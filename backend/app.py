"""SQLite read APIs and deterministic personalized recommendation."""

import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from .recommendation import PreferenceError, recommend


class RecommendRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    budget: float | None = None
    max_distance_m: float | None = None
    min_rating: float | None = None
    tastes: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    meal_period: str | None = None
    only_open: bool = False
    top_k: int = 5

from .data.database import DEFAULT_DB
from .data.repository import FoodRepository
from .data.restrictions import AVOID_OPTIONS
from .data.validation import MEALS, TASTES, DataValidationError


def create_app(db_path=DEFAULT_DB):
    app = FastAPI(title="校园食光 CampusBite", version="0.3.0")
    app.state.db_path = Path(db_path)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc):
        return JSONResponse(status_code=422, content={"error": {"code": "INVALID_INPUT", "message": "输入格式不正确，请检查预算、距离及筛选条件。"}})

    @app.exception_handler(DataValidationError)
    async def invalid_data(request: Request, exc):
        # Repository parameter validation is handled below; this signals stored data corruption.
        return JSONResponse(status_code=503, content={"error": {"code": "DATA_UNAVAILABLE", "message": "餐饮信息暂不可用，请稍后重试。"}})

    @app.exception_handler(FileNotFoundError)
    @app.exception_handler(sqlite3.Error)
    async def unavailable(request: Request, exc):
        return JSONResponse(status_code=503, content={"error": {"code": "DATA_UNAVAILABLE", "message": "餐饮信息暂不可用，请稍后重试。"}})

    def repository():
        return FoodRepository(app.state.db_path)

    @app.post("/api/recommend")
    def recommendations(preferences: RecommendRequest):
        from .recommendation import validate_preferences
        values = preferences.model_dump()
        try:
            validate_preferences(values)
        except PreferenceError as exc:
            return JSONResponse(status_code=422, content={"error": {"code": "INVALID_INPUT", "message": str(exc)}})
        repo = repository()
        return {**recommend(repo.dishes(), values), "metadata": repo.metadata()}

    @app.get("/api/restaurants")
    def restaurants():
        repo = repository()
        items = repo.restaurants()
        return {"items": items, "total": len(items), "metadata": repo.metadata()}

    @app.get("/api/dishes")
    def dishes(keyword: str = "", budget: Annotated[float | None, Query(gt=0, lt=1000000000)] = None,
               max_distance_m: Annotated[float | None, Query(ge=0)] = None,
               min_rating: Annotated[float | None, Query(ge=0, le=5)] = None,
               taste: str | None = None, meal_period: str | None = None, cuisine: str | None = None,
               only_open: bool = False, sort: str = "id", avoid: Annotated[list[str] | None, Query()] = None):
        if (taste is not None and taste not in TASTES) or (meal_period is not None and meal_period not in MEALS) or sort not in {"id", "price", "distance", "rating"} or (cuisine is not None and not cuisine.strip()):
            return JSONResponse(status_code=422, content={"error": {"code": "INVALID_INPUT", "message": "筛选选项不受支持，请重新选择。"}})
        from .data.validation import number
        try:
            if budget is not None:
                number(budget, "budget", money=True)
            if max_distance_m is not None:
                number(max_distance_m, "max_distance_m")
            if any(not term.strip() for term in avoid or []):
                raise DataValidationError("忌口条件不能为空")
        except DataValidationError as exc:
            return JSONResponse(status_code=422, content={"error": {"code": "INVALID_INPUT", "message": str(exc)}})
        repo = repository()
        items = repo.dishes(keyword=keyword, budget=budget, max_distance_m=max_distance_m,
                            min_rating=min_rating, taste=taste, meal_period=meal_period,
                            only_open=only_open, sort=sort, cuisine=cuisine, avoid=avoid)
        all_items = repo.dishes()
        return {"items": items, "total": len(items), "metadata": repo.metadata(),
                "options": {"cuisines": sorted({item["cuisine"] for item in all_items}),
                            "tastes": sorted(TASTES), "meal_periods": sorted(MEALS), "avoid": AVOID_OPTIONS}}

    @app.get("/api/dishes/{dish_id}")
    def detail(dish_id: int):
        if dish_id <= 0:
            return JSONResponse(status_code=422, content={"error": {"code": "INVALID_INPUT", "message": "菜品编号须为正整数。"}})
        repo = repository()
        item = repo.dish(dish_id)
        if item is None:
            return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND", "message": "这道菜品不存在。"}})
        return {"item": item, "metadata": repo.metadata()}

    return app


app = create_app()
