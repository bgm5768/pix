from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ComicStudioProjectCreate(BaseModel):
    title: str = Field(default="새 만화", min_length=1, max_length=120)
    model: str = Field(default="", max_length=260)
    plan_yaml: str | None = None


class ComicStudioProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    model: str | None = Field(default=None, max_length=260)
    plan_yaml: str | None = None


class ComicStudioGenerateRequest(BaseModel):
    seeds: str | list[int] | None = None
    count: int = Field(default=1, ge=1, le=6)
    model: str | None = Field(default=None, max_length=260)
    steps: int | None = Field(default=None, ge=1, le=150)
    cfg: float | None = Field(default=None, ge=0, le=30)
    width: int | None = Field(default=None, ge=256, le=2048)
    height: int | None = Field(default=None, ge=256, le=2048)
    negative_extra: str = Field(default="", max_length=4000)
    prompt_extra: str = Field(default="", max_length=4000)
    sampler: str | None = Field(default=None, max_length=40)
    scheduler: str | None = Field(default=None, max_length=40)


class ComicStudioPickRequest(BaseModel):
    candidate: str = Field(min_length=1, max_length=200)


class ComicStudioPageRequest(BaseModel):
    page: int = Field(ge=1, le=999)
    layout: str | None = Field(default=None, max_length=20)
    width: int = Field(default=1240, ge=600, le=2400)
    height: int = Field(default=1754, ge=600, le=3400)
    title: str | None = Field(default=None, max_length=200)


class ComicStudioCharacterInput(BaseModel):
    id: str = Field(
        min_length=2,
        max_length=90,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    name: str = Field(default="", max_length=120)
    adult: bool = True
    gender: Literal["female", "male", "other"] = "female"
    tags: str = Field(min_length=1, max_length=4000)
    default_outfit: str = Field(default="", max_length=2000)
    negative: str = Field(default="", max_length=2000)
    description: str = Field(default="", max_length=2000)
