import yaml

from app.services.org_skill_adapter import _workflow_markdown, _workflow_node_kind, _workflow_nodes
from app.services.skill_assets.composite_task import build_subtasks, parse_composite_skill


def test_browser_workflow_node_survives_adapter_and_compiles_to_submit() -> None:
    nodes = _workflow_nodes({
        "workflowNodes": [{
            "id": "wechat-draft",
            "type": "browser_automation",
            "title": "保存微信公众号草稿",
            "description": "进入草稿箱，添加文章并保存草稿，不要发布",
            "businessConfig": {
                "targetName": "微信公众号后台",
                "targetUrl": "https://mp.weixin.qq.com/",
                "outputAlias": "公众号草稿",
            },
        }],
    })

    assert len(nodes) == 1
    assert nodes[0]["type"] == "browser_automation"
    assert nodes[0]["businessConfig"]["targetName"] == "微信公众号后台"
    assert nodes[0]["businessConfig"]["targetUrl"] == "https://mp.weixin.qq.com/"
    assert _workflow_node_kind(nodes[0]) == "browser.submit"

    markdown = _workflow_markdown(
        name="公众号发布准备",
        description="生成文章并保存到草稿箱",
        scenario="公众号运营",
        steps=[nodes[0]["description"]],
        nodes=nodes,
    )
    frontmatter = yaml.safe_load(markdown.split("---", 2)[1])
    assert frontmatter["steps"][0]["kind"] == "browser.submit"
    assert frontmatter["steps"][0]["semantic_config"]["targetName"] == "微信公众号后台"
    assert frontmatter["steps"][0]["semantic_config"]["targetUrl"] == "https://mp.weixin.qq.com/"

    parsed = parse_composite_skill(markdown)
    subtasks = build_subtasks(steps=parsed["steps"], site_profile_lookup={})
    assert subtasks[0]["meta"]["entry_url"] == "https://mp.weixin.qq.com/"
    assert "[目标系统: 微信公众号后台 (https://mp.weixin.qq.com/)]" in subtasks[0]["objective"]
    assert subtasks[0]["meta"]["site_name"] == "微信公众号后台"
