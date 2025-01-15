import { useMemo, useState } from "react";
import BackToCollection from "./BackToCollection";
import { TableHeader, TableRow } from "./Crawler";
import ControlledTable from "../ControlledTable/ControlledTable";
import useKeyboardShortcut from "@/utils/keyboard";
import styles from './Crawler.module.css'
import FakeCheckbox from "../form/FakeCheckbox";


export default function SearchEngine({ assetId, slideToLeft }) {

    const [websites, setWebsites] = useState([])
    const [websitesLoadState, setWebsitesLoadState] = useState(0)
    const resultLimit = 20

    const [selected, setSelected] = useState({})  // URL -> 1 or 0

    function getUrl(page, text){
        if (!text){
            text = ""
        }
        let url = new URL(process.env.NEXT_PUBLIC_BACKEND_URL + "/crawler/web")
        let params = new URLSearchParams(url.search);
        const offset = resultLimit * (page - 1)
        let paramObj = {
            'query': text,
            'limit': resultLimit,
            'offset': offset,
            'id': assetId
        }
        for (let key in paramObj) {
            params.append(key, paramObj[key]);
        }
        url.search = params.toString()
        return url
    }

    const tableCols = useMemo(() => {
        return [
            {'title': '', 'key': 'selected', 'flex': 1, 'hook': ({ item }) => {
                const isSelected = selected[item['url']]
                return (
                    <FakeCheckbox value={isSelected} setValue={(x) => setSelected({...selected, [item['url']]: x})} />
                )
            }, 'headerHook': ({}) => {
                const allSelected = websites.filter((x) => selected[x.url]).length == websites.length
                return (
                    <FakeCheckbox value={allSelected} setValue={(x) => {
                        const newSelected = {...selected}
                        for (const site of websites){
                            newSelected[site.url] = x
                        }
                        setSelected(newSelected)
                    }} />
                )
            }},
            {'title': 'Name', 'key': 'name', 'flex': 10},
            {'title': 'URL', 'key': 'url', 'flex': 10, 'hook': ({ item }) => {
                return (
                    <a href={item['url']} className={styles.urlLink}>{item['url']}</a>
                )
            }},
            {'title': 'Snippet', 'key': 'snippet', 'flex': 10}
        ]
    }, [selected, websites])

    useKeyboardShortcut([['ArrowLeft']], slideToLeft, false)

    function makeRow(item, i) {
        return <TableRow key={i} setItem={() => {}} item={item} i={i} isFirst={ i == 0} isLast={i == websites?.length - 1} tableCols={tableCols} />
    }

    return (
        <div style={{'display': 'flex', 'flexDirection': 'column', 'height': '100%', 'gap': '1rem'}}>
            <div style={{'display': 'flex'}}>
                <BackToCollection slideToLeft={slideToLeft} />
            </div>
            <div style={{'height': '100%', 'minHeight': '0px'}}>
                <ControlledTable
                    items={websites}
                    setItems={setWebsites}
                    loadingState={websitesLoadState}
                    setLoadingState={setWebsitesLoadState}
                    makeRow={makeRow}
                    limit={resultLimit}
                    getUrl={getUrl}
                    loadingSkeleton={'default-small'}
                    searchable={true}
                    tableHeader={(<TableHeader cols={tableCols} />)}
                    gap={'0px'}
                    flexWrap="noWrap"
                    scroll={true}
                    customNoResults={(
                        <div style={{'height': '100%', 'width': '100%', 'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center', 'fontSize': '1.15rem'}}>
                            Nothing yet.
                        </div>
                    )}
                    searchAutoComplete={false}
                    customDisplayWrapperStyle={{'borderRadius': 'var(--medium-border-radius)', 'overflow': 'hidden', 'border': '1px solid var(--light-border)', 'backgroundColor': 'var(--light-primary)'}}
                />
            </div>
        </div>
    )
}
