import requests
from markdownify import MarkdownConverter
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from .retriever import Chunk
import re
from urllib.parse import urljoin
import sys
from .integrations.web import SearchEngine, SearchResult, SEARCH_PROVIDERS
from .integrations.file_loaders import get_loader, TextSplitter, RawChunk
from .user import get_user_search_engine_code
from .auth import User
from .utils import ntokens_to_nchars, get_token_estimate
import tempfile


class WebChunk(Chunk):
    url: str
    image: str
    favicon: str
    def __init__(self, index, source_name, txt, url, image="", favicon="", embedding=None) -> None:
        self.txt = txt
        self.url = url
        self.image = image
        self.favicon = favicon
        super().__init__(index, source_name, txt, embedding=embedding)
    
    def to_json(self):
        regular = super().to_json()
        regular['url'] = self.url
        if self.image:
            regular['image'] = self.image
        if self.favicon:
            regular['favicon'] = self.favicon
        return regular


class CustomMarkdownConverter(MarkdownConverter):
    def convert(self, soup, strip=None):
        if strip is not None:
            for tag in strip:
                for element in soup.find_all(tag):
                    element.decompose()
            html = str(soup)
        return super().convert(html)
    
    def convert_iframe(self, el, text, convert_as_inline):
        # Extract the 'src' attribute from the iframe
        src = el.get('src')
        if src:
            return f'\n\n[Click to View Embedded Content]({src})\n\n'
        return ''
    
    def convert_pre(self, el, text, convert_as_inline):
        # Custom handling for <pre> tags
        return f'\n```\n{text}\n```\n'

    def convert_code(self, el, text, convert_as_inline):
        # Custom handling for <code> tags
        return f'`{text}`'


# Returns json object with keys:
# "success", and if failed: "reason"; "title", "ext", "data", "image_url" (optional)
# to_string => data must be string (returns Markdown)
# Set use_html to prevent a request altogether and just have it process the HTML
def scrape(url, use_html=None, just_text=False, reduce_whitespace=False):
    to_return = {}
    try:
        if not use_html:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
                'Accept': 'application/json, text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9'
            }
            response = requests.get(url, headers=headers, timeout=5)
            response.raise_for_status()  # will throw an error if the request isn't good
            content_type = response.headers.get('Content-Type', '').split(';')[0]
            website_data = response.content
        else:
            content_type = "text/html"
            website_data = use_html

        if content_type == 'application/pdf':
            to_return['ext'] = 'pdf'
            to_return['data'] = website_data
        else:
            to_return['ext'] = 'txt' if just_text else 'md'
            # Convert the HTML content to a BeautifulSoup object
            soup = BeautifulSoup(website_data, 'html.parser')
            if soup.title.string:
                to_return['title'] = soup.title.string

            # Get preview description
            description = None
            # Check Open Graph description first
            og_description = soup.find('meta', attrs={'property': 'og:description', 'content': True})
            if og_description:
                description = og_description['content']
            # Fallback to meta description if og:description not found
            if not description:
                meta_description = soup.find('meta', attrs={'name': 'description', 'content': True})
                if meta_description:
                    description = meta_description['content']
            if description:
                to_return['description'] = description

            author = None
            # Check Open Graph author first
            og_author = soup.find('meta', attrs={'property': 'og:author', 'content': True})
            if og_author:
                author = og_author['content']
            # Fallback to meta author if og:description not found
            if not author:
                meta_author = soup.find('meta', attrs={'name': 'author', 'content': True})
                if meta_author:
                    author = meta_author['content']
            if author:
                to_return['author'] = author

            image_url = None
            # Check Open Graph image first
            og_image = soup.find('meta', attrs={'property': 'og:image', 'content': True})
            if og_image:
                image_url = og_image['content']
            # Fallback to Twitter image if og:image not found
            if not image_url:
                twitter_image = soup.find('meta', attrs={'name': 'twitter:image', 'content': True})
                if twitter_image:
                    image_url = twitter_image['content']

            # Fetching favicon
            favicon = soup.find('link', rel=lambda x: x and x.lower() in ['icon', 'shortcut icon'])
            favicon_url = favicon['href'] if favicon and favicon.has_attr('href') else None
            if favicon_url:
                # Resolving the favicon URL against the base URL
                to_return['favicon'] = urljoin(url, favicon_url)

            if image_url:
                to_return['image_url'] = image_url

            if just_text:
                to_return['data'] = soup.get_text()
            else:
                converter = CustomMarkdownConverter()
                to_return['data'] = converter.convert(soup, strip=['script', 'style'])
            
            if reduce_whitespace:
                to_return['data'] = re.sub(r'\n[\n]+', '\n\n', to_return['data'])  # Turns repeated new lines into just one
        

    except requests.RequestException as e:
        print(e, file=sys.stderr)
        return {'success': False, 'reason': 'Failed to scrape website (request exception)'}
    except Exception as e:
        print(e, file=sys.stderr)
        return {'success': False, 'reason': 'Failed to scrape website'}

    return {'success': True, **to_return}


def get_web_chunks(user: User, search_query, available_context, max_n=5):
    se_code = get_user_search_engine_code(user)
    se: SearchEngine = SEARCH_PROVIDERS[se_code]
    results: list[SearchResult] = se.search(search_query)
    
    # Scrape each site in parallel
    scrape_responses = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_search_result = {executor.submit(scrape, result.url, just_text=True, reduce_whitespace=True): result for result in results}
        for future in as_completed(future_to_search_result):
            res = future_to_search_result[future]
            try:
                data = future.result()
                if data:
                    if 'title' not in data:
                        data['title'] = res.name
                    data['url'] = res.url
                    scrape_responses.append(data)
            except Exception as exc:
                print('Exception in get_web_chunks: %r generated an exception: %s' % (res.url, exc))
    
    scrape_responses = scrape_responses[:max_n]
    
    if not len(scrape_responses):
        return []
    
    per_source_max_tokens = available_context // len(scrape_responses)

    # Process and divide each source
    chunks = []
    for scrape_result in scrape_responses:
        text = ""
        if scrape_result['success'] and scrape_result['ext'] == 'txt':
            text = scrape_result['data']
            # Instead of simply truncating, we do the middle of the page, which is better for websites (nav bar + footer ...)
            # Uses len for speed
            truncate_chars = ntokens_to_nchars(per_source_max_tokens)
            opening_i = max((len(text) // 2) - truncate_chars // 2, 0)
            ending_i = truncate_chars + opening_i
            text = text[opening_i:ending_i]
        elif scrape_result['success'] and scrape_result['ext'] == 'pdf':
            pdf_data = scrape_result['data']
            cum_toks = 0
            try:
                tmp = tempfile.NamedTemporaryFile(delete=False)
                tmp.write(pdf_data)
                loader = get_loader('pdf', tmp.name)
                raw_chunks = loader.load_and_split(TextSplitter(max_chunk_size=ntokens_to_nchars(250), length_function=len))
                for raw_chunk in raw_chunks:
                    raw_chunk: RawChunk
                    ntoks = get_token_estimate(raw_chunk.page_content)  # very accurate estimate
                    if cum_toks + ntoks > per_source_max_tokens:
                        break
                    text += raw_chunk.page_content
                    cum_toks += ntoks
            finally:
                tmp.close()
        else:
            continue
        
        url = scrape_result['url']

        image = {'image': scrape_result['image_url']} if 'image_url' in scrape_result else {}
        favicon = {'favicon': scrape_result['favicon']} if 'favicon' in scrape_result else {}
        chunk = WebChunk(0, f"{scrape_result['title']} ({url})", text, url, **image, **favicon)
        chunks.append(chunk)

    return chunks
