import warnings
from ..configs.secrets import OPENAI_API_KEY, ANTHROPIC_API_KEY, OLLAMA_URL, OLLAMA_LMS, OPENAI_COMPATIBLE_URL, OPENAI_COMPATIBLE_KEY, OPENAI_COMPATIBLE_LMS
from ..utils import extract_from_base64_url
import os
import requests
import json

os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY if OPENAI_API_KEY else ""
from openai import OpenAI
openai_client = OpenAI() if OPENAI_API_KEY else None
import anthropic
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None


class LM():
    code: str = ""
    name: str = ""  # How users see the name presented
    desc: str = ""
    traits: str = ""  # A couple word description of strengths
    context_length: int  # in tokens
    accepts_images: bool
    supports_json: bool
    def __init__(self, code, name, desc, traits, context_length, accepts_images=False, supports_json=False) -> None:
        self.code = code
        self.name = name
        self.desc = desc
        self.traits = traits
        self.context_length = context_length
        self.accepts_images=accepts_images
        self.supports_json = supports_json

    def run(self, txt, system_prompt=None, context=[], make_json=False, temperature=None, images=[]):
        raise NotImplementedError(f"Run not impelemented for language model {self.code}")

    def stream(self, txt, system_prompt=None, context=[], temperature=None, images=[]):
        raise NotImplementedError(f"Stream not impelemented for language model {self.code}")

    def to_json_obj(self):
        return {
            'code': self.code,
            'name': self.name,
            'desc': self.desc,
            'traits': self.traits,
            'accepts_images': self.accepts_images,
            'context_length': self.context_length,
            'supports_json': self.supports_json
        }


class OpenAILM(LM):
    def __init__(self, openai_code, code, name, desc, traits, context_length, supports_json=False, accepts_images=False) -> None:
        self.openai_code = openai_code
        super().__init__(
            code=code,
            name=name,
            desc=desc,
            traits=traits,
            context_length=context_length,
            supports_json=supports_json,
            accepts_images=accepts_images
        )

    def _make_messages(self, txt, system_prompt=None, context=[], images=[]):
        messages = []
        messages.append({'role': 'system', 'content': system_prompt if system_prompt is not None else ""})

        for round in context:
            if 'images' in round and round['images'] and len(round['images']) and self.accepts_images:
                # Note that the "image_url" is actually a base64 string with data:image/png;base64,...
                messages.append({'role': 'user', 'content': [{'type': 'text', 'text': round['user']}, *[{'type': 'image_url', 'image_url': {'url': x}} for x in round['images']]]})
            else:
                messages.append({'role': 'user', 'content': round['user']})
            messages.append({'role': 'assistant', 'content': round['ai']})

        if images is not None and self.accepts_images and len(images):
            messages.append({'role': 'user', 'content': [{'type': 'text', 'text': txt}, *[{'type': 'image_url', 'image_url': {'url': x}} for x in images]]})
        else:
            messages.append({'role': 'user', 'content': txt})

        return messages


    def run(self, txt, system_prompt=None, context=[], temperature=.7, make_json=False, images=[]):

        messages = self._make_messages(
            txt=txt,
            system_prompt=system_prompt,
            context=context,
            images=images
        )

        extra_kwargs = {}
        if temperature is not None:
            extra_kwargs['temperature'] = temperature

        if make_json and self.supports_json:
            extra_kwargs['response_format'] = {'type': 'json_object'}
        
        completion = openai_client.chat.completions.create(model=self.openai_code, messages=messages, stream=False, **extra_kwargs)
        return completion.choices[0].message.content


    def stream(self, txt, system_prompt=None, context=[], temperature=None, images=[]):
       
        messages = self._make_messages(
            txt=txt,
            system_prompt=system_prompt,
            context=context,
            images=images
        )

        extra_kwargs = {}
        if temperature is not None:
            extra_kwargs['temperature'] = temperature

        completion = openai_client.chat.completions.create(model=self.openai_code, messages=messages, stream=True, **extra_kwargs)
        for chunk in completion:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content


class Anthropic(LM):
    def __init__(self, model, code, name, desc, traits, context_length, supports_json=False, accepts_images=False) -> None:
        self.model = model
        super().__init__(
            code=code,
            name=name,
            desc=desc,
            traits=traits,
            context_length=context_length,
            supports_json=supports_json,
            accepts_images=accepts_images
        )

    def _make_messages(self, txt, system_prompt=None, context=[], images=[]):
        messages = []

        def get_images_content(imgs):
            image_content = []
            for x in imgs:
                media_type, img_data = extract_from_base64_url(x)
                image_content.append({'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': img_data}})
            return image_content

        for round in context:
            if 'images' in round and round['images'] and len(round['images']) and self.accepts_images:
                messages.append(
                    {
                        'role': 'user', 
                        'content': [
                            {'type': 'text', 'text': round['user']},
                            *get_images_content(round['images'])
                        ]
                    }
                )
            else:
                messages.append({'role': 'user', 'content': round['user']})
            messages.append({'role': 'assistant', 'content': round['ai']})

        if images is not None and self.accepts_images and len(images):
            messages.append(
                {
                    'role': 'user', 
                    'content': [
                        {'type': 'text', 'text': txt},
                        *get_images_content(images)
                    ]
                }
            )
        else:
            messages.append({'role': 'user', 'content': txt})

        return messages


    def run(self, txt, system_prompt=None, context=[], temperature=.7, make_json=False, images=[]):
        
        messages = self._make_messages(
            txt=txt,
            system_prompt=system_prompt,
            context=context,
            images=images
        )

        if temperature is None:
            temperature = .7

        if system_prompt is None:
            system_prompt = ""

        if make_json:
            messages.append({'role': 'assistant', 'content': '{"'})  # best we can do - just starting the thing off with {" (NOTE: inverse at bottom!)

        # Max content window is 200k for claude 3
        message = client.messages.create(
            max_tokens=4096,  # max output tokens?
            messages=messages,
            model=self.model,
            temperature=temperature,
            system=system_prompt
        )
        
        resp = message.content[0].text

        if make_json:
            resp = '{"' + resp

        return resp

    def stream(self, txt, system_prompt=None, context=[], temperature=None, images=[]):
        messages = self._make_messages(
            txt=txt,
            system_prompt=system_prompt,
            context=context,
            images=images
        )

        if temperature is None:
            temperature = .7

        if system_prompt is None:
            system_prompt = ""

        # Max content window is 200k for claude 3
        with client.messages.stream(
            max_tokens=4096,  # max output tokens?
            messages=messages,
            model=self.model,
            temperature=temperature,
            system=system_prompt
        ) as stream:
            for text in stream.text_stream:
                yield text


class Ollama(LM):
    def __init__(self, ollama_code, code, name, desc, traits, context_length, supports_json=True, accepts_images=False) -> None:
        self.model = ollama_code
        super().__init__(
            code=code,
            name=name,
            desc=desc,
            traits=traits,
            context_length=context_length,
            supports_json=supports_json,
            accepts_images=accepts_images
        )

    def _make_messages(self, txt, system_prompt=None, context=[], images=[]):
        messages = []

        if system_prompt:
            messages.append({
                'role': 'system',
                'content': system_prompt
            })

        def get_images_content(imgs):
            image_content = []
            for x in imgs:
                _, img_data = extract_from_base64_url(x)
                image_content.append(img_data)
            return image_content

        for round in context:
            messages.append({
                'role': 'user', 
                'content': round['user'],
                'images': get_images_content(round['images']) if 'images' in round and round['images'] and len(round['images']) and self.accepts_images else None
            })
            messages.append({'role': 'assistant', 'content': round['ai']})

        messages.append({
            'role': 'user', 
            'content': txt,
            'images': get_images_content(round['images']) if images is not None and self.accepts_images and len(images) else None
        })
        return messages

    def run(self, txt, system_prompt=None, context=[], temperature=.7, make_json=False, images=[]):
        messages = self._make_messages(txt, system_prompt=system_prompt, context=context, images=images)
        params = {
            'model': self.model,
            'messages': messages,
            'options': {
                'temperature': temperature if temperature else .7
            },
            'stream': False
        }
        url = f'{OLLAMA_URL}/api/chat'
        response = requests.post(url, json=params, stream=False)
        response.raise_for_status()  # Raise an error for bad responses
        my_json = response.json()
        x = my_json['message']['content']
        return x

    def stream(self, txt, system_prompt=None, context=[], temperature=None, images=[]):
        params = {
            'model': self.model,
            'messages': self._make_messages(txt, system_prompt=system_prompt, context=context, images=images),
            'options': {
                'temperature': temperature if temperature else .7,
                'num_ctx': self.context_length
            },
            'stream': True
        }
        url = f'{OLLAMA_URL}/api/chat'
        try:
            response = requests.post(url, json=params, stream=True)
            response.raise_for_status()  # Raise an error for bad responses

            # Process the streaming response
            for line in response.iter_lines():
                if line:
                    # Assuming each line is a JSON object
                    data = line.decode('utf-8')
                    my_json = json.loads(data)
                    # Process the data as needed
                    yield my_json['message']['content']

        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")


class OpenAICompatibleLM(LM):
    def __init__(self, model_code, code, name, desc, traits, context_length, supports_json=False, accepts_images=False) -> None:
        self.model_code = model_code
        super().__init__(
            code=code,
            name=name,
            desc=desc,
            traits=traits,
            context_length=context_length,
            supports_json=supports_json,
            accepts_images=accepts_images
        )

    def _make_messages(self, txt, system_prompt=None, context=[], images=[]):
        messages = []
        messages.append({'role': 'system', 'content': system_prompt if system_prompt is not None else ""})

        for round in context:
            if 'images' in round and round['images'] and len(round['images']) and self.accepts_images:
                # Note that the "image_url" is actually a base64 string with data:image/png;base64,...
                messages.append({'role': 'user', 'content': [{'type': 'text', 'text': round['user']}, *[{'type': 'image_url', 'image_url': {'url': x}} for x in round['images']]]})
            else:
                messages.append({'role': 'user', 'content': round['user']})
            messages.append({'role': 'assistant', 'content': round['ai']})

        if images is not None and self.accepts_images and len(images):
            messages.append({'role': 'user', 'content': [{'type': 'text', 'text': txt}, *[{'type': 'image_url', 'image_url': {'url': x}} for x in images]]})
        else:
            messages.append({'role': 'user', 'content': txt})

        return messages


    def run(self, txt, system_prompt=None, context=[], temperature=.7, make_json=False, images=[]):

        messages = self._make_messages(
            txt=txt,
            system_prompt=system_prompt,
            context=context,
            images=images
        )

        extra_kwargs = {}
        if temperature is not None:
            extra_kwargs['temperature'] = temperature

        if make_json and self.supports_json:
            extra_kwargs['response_format'] = {'type': 'json_object'}
        
        params = {
            'model': self.model_code,
            'messages': messages,
            'temperature': temperature if temperature else .7,
            'stream': False
        }
        url = f'{OPENAI_COMPATIBLE_URL}/v1/chat/completions'
        response = requests.post(url, headers={'Authorization': f'Bearer {OPENAI_COMPATIBLE_KEY}'}, json=params, stream=False)
        response.raise_for_status()  # Raise an error for bad responses
        my_json = response.json()
        return my_json['choices'][0]['message']['content']
        

    def stream(self, txt, system_prompt=None, context=[], temperature=None, images=[]):
       
        messages = self._make_messages(
            txt=txt,
            system_prompt=system_prompt,
            context=context,
            images=images
        )

        extra_kwargs = {}
        if temperature is not None:
            extra_kwargs['temperature'] = temperature

        params = {
            'model': self.model_code,
            'messages': messages,
            'temperature': temperature if temperature else .7,
            'stream': True
        }

        url = f'{OPENAI_COMPATIBLE_URL}/v1/chat/completions'
        response = requests.post(url, headers={'Authorization': f'Bearer {OPENAI_COMPATIBLE_KEY}'}, json=params, stream=True)
        response.raise_for_status()  # Raise an error for bad responses

        # Process the streaming response
        for line in response.iter_lines():
            if line:
                data = line.decode('utf-8')
                real_data = data[len('data: '):]
                if real_data == '[DONE]':
                    break
                my_json = json.loads(real_data)
                delta = my_json['choices'][0]['delta']
                if 'content' in delta:
                    yield delta['content']


class GPT4(OpenAILM):
    def __init__(self) -> None:
        super().__init__(
            openai_code='gpt-4',
            code='gpt-4',
            name='GPT-4',
            desc='GPT-4 is among the most powerful models of intelligence on the planet.',
            traits="Smart",
            context_length=8_192,
            supports_json=True,
            accepts_images=False
        )


class GPT4o(OpenAILM):
    def __init__(self) -> None:
        super().__init__(
            openai_code='gpt-4o',
            code='gpt-4o',
            name='GPT-4o',
            desc='GPT-4o is a flagship model from OpenAI, which is very fast, very smart, and natively multimodal.',
            traits="Very Smart and Fast",
            context_length=128_000,
            supports_json=True,
            accepts_images=True
        )


class GPT35Turbo(OpenAILM):
    def __init__(self) -> None:
        super().__init__(
            openai_code='gpt-3.5-turbo',
            code='gpt-3.5-turbo',
            name='GPT-3.5 Turbo',
            desc="GPT 3.5 is fast and often adequate for straightforward document Q&A.",
            traits="Fast",
            context_length=16_385,
            supports_json=True,
            accepts_images=False
        )


class GPT4Turbo(OpenAILM):
    def __init__(self) -> None:
        super().__init__(
            openai_code='gpt-4-turbo',
            code='gpt-4-turbo',
            name='GPT-4 Turbo',
            desc="GPT 4 Turbo sits between 3.5 and 4 for speed and intelligence, so some argue that it is faster than 4.",
            traits="Smart and Fast",
            context_length=128_000,
            supports_json=True,
            accepts_images=True
        )


class GPT4oMini(OpenAILM):
    def __init__(self) -> None:
        super().__init__(
            openai_code='gpt-4o-mini',
            code='gpt-4o-mini',
            name='GPT-4o Mini',
            desc="GPT 4o mini is slim and fast.",
            traits="Fast",
            context_length=128_000,
            supports_json=True,
            accepts_images=True
        )


class O1Preview(OpenAILM):
    def __init__(self) -> None:
        super().__init__(
            openai_code='o1-preview',
            code='o1-preview',
            name='O1 Preview',
            desc="O1 is an experimental, slow, but highlly intelligent model by OpenAI.",
            traits="Slow and Smart",
            context_length=128_000,
            supports_json=True,
            accepts_images=True
        )


class O1Mini(OpenAILM):
    def __init__(self) -> None:
        super().__init__(
            openai_code='o1-mini',
            code='o1-mini',
            name='O1 Mini',
            desc="O1 Mini is an experimental, slow, but highlly intelligent model by OpenAI. It is smaller and faster than O1 Preview.",
            traits="Slow and Smart",
            context_length=128_000,
            supports_json=True,
            accepts_images=True
        )


class Claude3Opus(Anthropic):
    def __init__(self) -> None:
        super().__init__(
            model='claude-3-opus-latest',
            code='claude-3-opus',
            name='Claude 3 Opus',
            desc="Released in early 2024, Opus was the first broadly available non-OpenAI model to rival GPT-4 in intelligence.",
            traits="Smart",
            context_length=200_000,
            supports_json=True,
            accepts_images=True
        )


class Claude35Sonnet(Anthropic):
    def __init__(self) -> None:
        super().__init__(
            model='claude-3-5-sonnet-20240620',
            code='claude-3-5-sonnet',
            name='Claude 3.5 Sonnet',
            desc="It is powerful iteration of the intermediate level model in the latest Claude 3.5 lineup, rivaling GPT-4o. It is especially good for writing code.",
            traits="Coding",
            context_length=200_000,
            supports_json=True,
            accepts_images=True
        )


# Unlike others, ollama model objects are made from environment variables.
def gen_ollama_lms():

    if not OLLAMA_URL or not OLLAMA_LMS:
        return []
    
    ollama_lms = json.loads(OLLAMA_LMS)
    if not len(ollama_lms):
        return []

    # Just check to make sure ollama URL is setup correctly.
    url = f'{OLLAMA_URL}/api/tags'
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Could not retrieve ollama models at {OLLAMA_URL}. Maybe you should change the URL? See manual setup in the README.")

    # TODO: confirm that all the models are downloaded / available.

    models = []
    for model in ollama_lms:
        code = model['code']
        models.append(Ollama(
            ollama_code=code,
            code=f'{code}-ollama',
            name=code,
            desc=f'{code} is an open source edge model run via Ollama.',
            traits="Open Source",
            context_length=model['context_length'],
            supports_json=True,
            accepts_images=model['vision']
        ))
    return models

ollama_models = {x.code: x for x in gen_ollama_lms()}


# Unlike others, ollama model objects are made from environment variables.
def gen_openai_compatible_lms():

    if not OPENAI_COMPATIBLE_URL or not OPENAI_COMPATIBLE_LMS:
        return []
    
    openai_compatible_lms = json.loads(OPENAI_COMPATIBLE_LMS)
    if not len(openai_compatible_lms):
        return []

    # TODO: confirm that all the models are downloaded / available.
    models = []
    for model in openai_compatible_lms:
        code = model['code']
        models.append(OpenAICompatibleLM(
            model_code=code,
            code=f'{code}-oai-compatible',
            name=code,
            desc=f'{code} is running via an OpenAI Compatible API',
            traits="API",
            context_length=model['context_length'],
            supports_json=True,
            accepts_images=model['vision']
        ))
    return models

openai_compatible_models = {x.code: x for x in gen_openai_compatible_lms()}


LM_PROVIDERS = {
    'gpt-4': GPT4(),
    'gpt-4o-mini': GPT4oMini(),
    'gpt-4-turbo': GPT4Turbo(),
    'claude-3-opus': Claude3Opus(),
    'claude-3-5-sonnet': Claude35Sonnet(),
    'gpt-4o': GPT4o(),
    # Add the generated models
    **ollama_models,
    **openai_compatible_models,
    # o1-preview and o1-mini don't yet support system prompts, images, and streaming - so they are disabled in user_config.
    'o1-preview': O1Preview(),
    'o1-mini': O1Mini()
}


"""

Percentage of context length that should be used for retrieval in various places in the code base.

Not necessarily used in non chat retrieval contexts.

Can / should be changed based on typical model behavior and speed.

Sample outputs:
- 5_000 -> 2_500
- 10_000 -> 7_000
- 32_000 -> 23_500
- 100_000 -> 57_500
- 200_000 -> 107_500

"""
def get_safe_retrieval_context_length(model: LM):
    # Works like tax brackets
    brackets = [
        (5_000, .5),  # 50% of the first 5000 tokens
        (10_000, .9),  # 90% of tokens 5000-10000
        (32_000, .75),  # etc
        (100_000, .5)
    ]
    cl_remaining = model.context_length
    safety_cl = 0
    prev = 0
    for bracket in brackets:
        overlap = min(cl_remaining, bracket[0] - prev)
        contribution = overlap * bracket[1]
        safety_cl += contribution
        cl_remaining -= bracket[0] - prev
        prev = bracket[0]
        if cl_remaining <= 0:
            break
    
    if cl_remaining > 0:
        safety_cl += cl_remaining * brackets[-1][1]

    return round(safety_cl)
