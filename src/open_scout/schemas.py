from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContentOptions(StrictModel):
    text: bool = True
    highlights: bool = True
    maxCharacters: int = Field(default=20000, ge=100, le=100000)


class SearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    type: Literal["auto", "keyword", "neural", "hybrid"] = "auto"
    numResults: int = Field(default=10, ge=1, le=50)
    includeDomains: list[str] = Field(default_factory=list, max_length=50)
    excludeDomains: list[str] = Field(default_factory=list, max_length=50)
    contents: ContentOptions = Field(default_factory=ContentOptions)

    @field_validator("query")
    @classmethod
    def clean_query(cls, value):
        if not value.strip():
            raise ValueError("Query cannot be blank")
        return value.strip()


class ContentsRequest(StrictModel):
    urls: list[str] = Field(min_length=1, max_length=50)
    text: bool = True
    highlights: bool = True
    maxCharacters: int = Field(default=20000, ge=100, le=100000)


class SimilarRequest(StrictModel):
    url: str = Field(min_length=1, max_length=2048)
    numResults: int = Field(default=10, ge=1, le=50)
    includeDomains: list[str] = Field(default_factory=list, max_length=50)
    excludeDomains: list[str] = Field(default_factory=list, max_length=50)


class CrawlRequest(StrictModel):
    urls: list[str] = Field(min_length=1, max_length=10)
    maxPages: int = Field(default=20, ge=1, le=200)
    maxDepth: int = Field(default=1, ge=0, le=3)
