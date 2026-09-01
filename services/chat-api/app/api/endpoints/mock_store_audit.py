from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/mock/store-audit", tags=["mock-store-audit"])


class ApiResponse(BaseModel):
    code: int = 0
    message: Optional[str] = None
    data: Optional[object] = None


def _period_label(period: str) -> str:
    if period == "current":
        return "2026-06"
    return period or "2026-06"


def _task_rows(period: str) -> list[dict[str, Any]]:
    period = _period_label(period)
    return [
        {
            "task_id": f"{period}-audit-sh-xuhui",
            "store_id": "store-sh-xuhui",
            "store_name": "上海徐汇店",
            "audit_type": "月度综合巡检",
        },
        {
            "task_id": f"{period}-audit-sh-pudong",
            "store_id": "store-sh-pudong",
            "store_name": "上海浦东店",
            "audit_type": "月度综合巡检",
        },
        {
            "task_id": f"{period}-audit-hz-westlake",
            "store_id": "store-hz-westlake",
            "store_name": "杭州西湖店",
            "audit_type": "月度综合巡检",
        },
        {
            "task_id": f"{period}-audit-nj-xinjiekou",
            "store_id": "store-nj-xinjiekou",
            "store_name": "南京新街口店",
            "audit_type": "月度综合巡检",
        },
        {
            "task_id": f"{period}-audit-sz-industrial-park",
            "store_id": "store-sz-industrial-park",
            "store_name": "苏州园区店",
            "audit_type": "月度综合巡检",
        },
    ]


def _task_detail_map(period: str) -> dict[str, dict[str, Any]]:
    period = _period_label(period)
    return {
        f"{period}-audit-sh-xuhui": {
            "task_id": f"{period}-audit-sh-xuhui",
            "period": period,
            "region": "华东",
            "store_id": "store-sh-xuhui",
            "store_name": "上海徐汇店",
            "audit_type": "月度综合巡检",
            "inspector": "张静",
            "audit_date": f"{period}-03",
            "sanitation": {
                "status": "good",
                "score": 92,
                "findings": ["后场清洁合格", "顾客触点区域无明显卫生隐患"],
            },
            "display": {
                "status": "good",
                "score": 90,
                "findings": ["新品陈列完整", "主推位价格签清晰"],
            },
            "inventory": {
                "status": "warning",
                "score": 81,
                "findings": ["两款常销商品安全库存偏低", "周转总体正常"],
            },
            "staffing": {
                "status": "good",
                "score": 88,
                "findings": ["高峰时段排班充足", "店长巡检记录完整"],
            },
            "equipment": {
                "status": "good",
                "score": 89,
                "findings": ["收银设备稳定", "冷柜温控正常"],
            },
            "rectification_status": {
                "status": "closed",
                "owner": "林悦",
                "deadline": f"{period}-10",
                "notes": "低库存问题已安排补货，本月无高风险项。",
            },
        },
        f"{period}-audit-sh-pudong": {
            "task_id": f"{period}-audit-sh-pudong",
            "period": period,
            "region": "华东",
            "store_id": "store-sh-pudong",
            "store_name": "上海浦东店",
            "audit_type": "月度综合巡检",
            "inspector": "李蓉",
            "audit_date": f"{period}-04",
            "sanitation": {
                "status": "critical",
                "score": 61,
                "findings": ["后场垃圾暂存区未按规定封闭", "操作间地面有油污积水"],
            },
            "display": {
                "status": "warning",
                "score": 74,
                "findings": ["促销主陈列缺价签", "新品端架补货不及时"],
            },
            "inventory": {
                "status": "critical",
                "score": 58,
                "findings": ["高频 SKU 缺货 11 项", "临期商品隔离不规范"],
            },
            "staffing": {
                "status": "warning",
                "score": 72,
                "findings": ["晚高峰值班不足", "新员工未完成巡检培训"],
            },
            "equipment": {
                "status": "critical",
                "score": 65,
                "findings": ["一台冷柜温度波动超标", "后仓监控设备连续两日异常"],
            },
            "rectification_status": {
                "status": "overdue",
                "owner": "周岩",
                "deadline": f"{period}-06",
                "notes": "上月设备整改延期，卫生与库存问题本月再次复发。",
            },
        },
        f"{period}-audit-hz-westlake": {
            "task_id": f"{period}-audit-hz-westlake",
            "period": period,
            "region": "华东",
            "store_id": "store-hz-westlake",
            "store_name": "杭州西湖店",
            "audit_type": "月度综合巡检",
            "inspector": "顾宁",
            "audit_date": f"{period}-05",
            "sanitation": {
                "status": "good",
                "score": 90,
                "findings": ["门店卫生整体达标"],
            },
            "display": {
                "status": "warning",
                "score": 79,
                "findings": ["旧款商品陈列面积过大", "新品专区导购标识不够突出"],
            },
            "inventory": {
                "status": "critical",
                "score": 63,
                "findings": ["滞销 SKU 过多，占压库存明显", "补货节奏与陈列策略未联动"],
            },
            "staffing": {
                "status": "good",
                "score": 86,
                "findings": ["盘点交接规范", "责任人明确"],
            },
            "equipment": {
                "status": "good",
                "score": 84,
                "findings": ["设备运行稳定"],
            },
            "rectification_status": {
                "status": "in_progress",
                "owner": "陈敏",
                "deadline": f"{period}-12",
                "notes": "库存结构调整方案已启动，但尚未完成旧款清理。",
            },
        },
        f"{period}-audit-nj-xinjiekou": {
            "task_id": f"{period}-audit-nj-xinjiekou",
            "period": period,
            "region": "华东",
            "store_id": "store-nj-xinjiekou",
            "store_name": "南京新街口店",
            "audit_type": "月度综合巡检",
            "inspector": "何清",
            "audit_date": f"{period}-07",
            "sanitation": {
                "status": "good",
                "score": 87,
                "findings": ["卖场卫生正常"],
            },
            "display": {
                "status": "warning",
                "score": 76,
                "findings": ["重点陈列缺少连带销售提示", "爆款区动线不清晰"],
            },
            "inventory": {
                "status": "warning",
                "score": 75,
                "findings": ["畅销 SKU 缺货 6 项", "补货响应偏慢"],
            },
            "staffing": {
                "status": "critical",
                "score": 66,
                "findings": ["高峰时段导购不足", "新员工对促销规则掌握不完整"],
            },
            "equipment": {
                "status": "good",
                "score": 85,
                "findings": ["关键设备可用"],
            },
            "rectification_status": {
                "status": "in_progress",
                "owner": "王珂",
                "deadline": f"{period}-11",
                "notes": "人员与销售转化问题已立项整改，但排班调整尚未落地。",
            },
        },
        f"{period}-audit-sz-industrial-park": {
            "task_id": f"{period}-audit-sz-industrial-park",
            "period": period,
            "region": "华东",
            "store_id": "store-sz-industrial-park",
            "store_name": "苏州园区店",
            "audit_type": "月度综合巡检",
            "inspector": "曹宇",
            "audit_date": f"{period}-08",
            "sanitation": {
                "status": "good",
                "score": 93,
                "findings": ["门店环境整洁"],
            },
            "display": {
                "status": "good",
                "score": 91,
                "findings": ["主陈列和端架执行到位"],
            },
            "inventory": {
                "status": "good",
                "score": 88,
                "findings": ["库存结构健康", "补货及时"],
            },
            "staffing": {
                "status": "good",
                "score": 90,
                "findings": ["班次安排稳定", "交接规范"],
            },
            "equipment": {
                "status": "good",
                "score": 92,
                "findings": ["设备巡检记录完整"],
            },
            "rectification_status": {
                "status": "closed",
                "owner": "赵宁",
                "deadline": f"{period}-09",
                "notes": "本期无待整改高风险问题。",
            },
        },
    }


@router.get("/tasks", response_model=ApiResponse)
async def get_store_audit_tasks(period: str = Query("current")) -> ApiResponse:
    return ApiResponse(
        data={
            "period": _period_label(period),
            "scope": "华东直营门店",
            "tasks": _task_rows(period),
        }
    )


@router.get("/task-detail", response_model=ApiResponse)
async def get_store_audit_task_detail(taskId: str = Query(..., min_length=1)) -> ApiResponse:
    period = "current"
    if "-audit-" in taskId:
        period = taskId.split("-audit-", 1)[0]
    detail = _task_detail_map(period).get(taskId)
    if not detail:
        raise HTTPException(status_code=404, detail="巡检工单不存在")
    return ApiResponse(data=detail)
