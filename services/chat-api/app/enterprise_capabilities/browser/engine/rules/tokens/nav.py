"""Cross-cutting navigation vocabularies.

Pagination, search, tab switching, load-more — primitives that any
task type (CRUD, form, scrape) may need to operate.
"""

NEXT = (
    "next", "forward",
    "下一页", "下一步", "继续",
    "xiayiye", "xiayibu",
    ">", "›", "→",
)
PREV = (
    "prev", "previous", "back",
    "上一页", "上一步", "返回", "后退",
    "shangyiye", "fanhui",
    "<", "‹", "←",
)
LOAD_MORE = (
    "more", "load more", "show more",
    "更多", "加载更多", "查看更多",
    "gengduo", "jiazai",
)
SEARCH = (
    "search", "find", "query", "filter",
    "搜索", "查找", "筛选", "过滤", "查询",
    "sousuo", "chazhao", "shaixuan",
)
