from collections.abc import Sequence
from typing import Any

from .client import NotionClient


class NotionSchemaCache:
    def __init__(self, client: NotionClient) -> None:
        self.client = client
        self._schemas: dict[str, dict[str, Any]] = {}

    async def get_schema(self, data_source_id: str) -> dict[str, Any]:
        if data_source_id not in self._schemas:
            self._schemas[data_source_id] = await self.client.retrieve_data_source(data_source_id)
        return self._schemas[data_source_id]

    async def get_title_property_name(self, data_source_id: str) -> str:
        schema = await self.get_schema(data_source_id)
        properties = schema.get("properties", {})
        for name, prop in properties.items():
            if prop.get("type") == "title":
                return str(name)
        return "title"

    async def get_relation_target_data_source_id(self, data_source_id: str, property_name: str) -> str | None:
        schema = await self.get_schema(data_source_id)
        properties = schema.get("properties", {})
        prop = properties.get(property_name)
        if not prop or prop.get("type") != "relation":
            return None
        rel = prop.get("relation", {})
        target = rel.get("data_source_id") or rel.get("database_id")
        return str(target) if target else None

    async def resolve_finance_properties(self, data_source_id: str, overrides: dict[str, str] | None = None) -> dict[str, str]:
        schema = await self.get_schema(data_source_id)
        properties = schema.get("properties", {})
        detected: dict[str, str] = {}

        # 1. Title property: exactly one property has type 'title'
        for name, prop in properties.items():
            if prop.get("type") == "title":
                detected["title"] = name
                break

        def find_by_type_and_names(prop_types: Sequence[str], candidate_names: Sequence[str]) -> str | None:
            norm_candidates = [c.casefold() for c in candidate_names]
            for name, prop in properties.items():
                if prop.get("type") in prop_types and name.casefold() in norm_candidates:
                    return str(name)
            for name, prop in properties.items():
                if prop.get("type") in prop_types:
                    n_lower = name.casefold()
                    if any(c in n_lower or n_lower in c for c in norm_candidates):
                        return str(name)
            return None

        def find_single_of_type(prop_type: str) -> str | None:
            matches = [name for name, prop in properties.items() if prop.get("type") == prop_type]
            return str(matches[0]) if len(matches) == 1 else None

        # 2. Amount property
        amount_candidates = ["amount", "金額", "費用", "價格", "price", "cost", "total", "花費"]
        amount_prop = find_by_type_and_names(["number"], amount_candidates) or find_single_of_type("number")
        if amount_prop:
            detected["amount"] = amount_prop

        # 3. Date property
        date_candidates = ["date", "日期", "時間", "交易日期", "時間戳記"]
        date_prop = find_by_type_and_names(["date"], date_candidates) or find_single_of_type("date")
        if date_prop:
            detected["date"] = date_prop

        # 4. Type property (select)
        type_candidates = ["type", "類型", "種類", "收支"]
        type_prop = find_by_type_and_names(["select"], type_candidates)
        if type_prop:
            detected["type"] = type_prop

        # 5. Category property (relation or select)
        cat_candidates = ["category", "類別", "分類", "項目分類"]
        cat_prop = find_by_type_and_names(["relation"], cat_candidates) or find_by_type_and_names(["select"], cat_candidates)
        if cat_prop:
            detected["category"] = cat_prop

        # 6. Account property (relation or select)
        acc_candidates = ["account", "帳戶", "帳號", "資產", "支付方式", "付款帳戶"]
        acc_prop = find_by_type_and_names(["relation"], acc_candidates) or find_by_type_and_names(["select"], acc_candidates)
        if acc_prop:
            detected["account"] = acc_prop

        if overrides:
            detected.update(overrides)

        return detected

    async def resolve_task_properties(self, data_source_id: str, overrides: dict[str, str] | None = None) -> dict[str, str]:
        schema = await self.get_schema(data_source_id)
        properties = schema.get("properties", {})
        detected: dict[str, str] = {}

        # 1. Title property
        for name, prop in properties.items():
            if prop.get("type") == "title":
                detected["title"] = name
                break

        def find_by_type_and_names(prop_types: Sequence[str], candidate_names: Sequence[str]) -> str | None:
            norm_candidates = [c.casefold() for c in candidate_names]
            for name, prop in properties.items():
                if prop.get("type") in prop_types and name.casefold() in norm_candidates:
                    return str(name)
            for name, prop in properties.items():
                if prop.get("type") in prop_types:
                    n_lower = name.casefold()
                    if any(c in n_lower or n_lower in c for c in norm_candidates):
                        return str(name)
            return None

        # Status
        status_prop = find_by_type_and_names(["status", "select"], ["status", "狀態", "進度"])
        if status_prop:
            detected["status"] = status_prop

        # Due date
        due_prop = find_by_type_and_names(["date"], ["due", "due date", "截止", "到期", "日期", "執行日期"])
        if not due_prop:
            matches = [name for name, prop in properties.items() if prop.get("type") == "date"]
            if len(matches) == 1:
                due_prop = str(matches[0])
        if due_prop:
            detected["due"] = due_prop

        # Priority
        priority_prop = find_by_type_and_names(["select", "status"], ["priority", "優先級", "優先度", "重要度"])
        if priority_prop:
            detected["priority"] = priority_prop

        # Description
        desc_prop = find_by_type_and_names(["rich_text"], ["description", "說明", "備註", "描述", "note", "notes"])
        if desc_prop:
            detected["description"] = desc_prop

        # Project
        proj_prop = find_by_type_and_names(["relation"], ["project", "專案", "項目"])
        if proj_prop:
            detected["project"] = proj_prop

        # Parent task
        parent_prop = find_by_type_and_names(["relation"], ["parent task", "parent", "母任務", "父任務", "上層任務"])
        if parent_prop:
            detected["parent_task"] = parent_prop

        # Assignee
        assignee_prop = find_by_type_and_names(["people"], ["assignee", "指派", "負責人", "人員"])
        if assignee_prop:
            detected["assignee"] = assignee_prop

        # Smart list
        smart_prop = find_by_type_and_names(["select"], ["smart list", "清單"])
        if smart_prop:
            detected["smart_list"] = smart_prop

        # Recur interval
        recur_prop = find_by_type_and_names(["number"], ["recur interval", "週期", "間隔"])
        if recur_prop:
            detected["recur_interval"] = recur_prop

        # Recur unit
        unit_prop = find_by_type_and_names(["select"], ["recur unit", "週期單位", "單位"])
        if unit_prop:
            detected["recur_unit"] = unit_prop

        # Recur days
        days_prop = find_by_type_and_names(["multi_select"], ["days (only if set to 1 day(s))", "recur days", "days", "星期"])
        if days_prop:
            detected["recur_days"] = days_prop

        if overrides:
            detected.update(overrides)

        return detected
