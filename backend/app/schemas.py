from pydantic import BaseModel, Field


class ListingInput(BaseModel):
    complex_id: int
    exclusive_area: float = Field(gt=0, description="전용면적 ㎡")
    floor: int | None = Field(default=None, description="해당 층")
    dong: str | None = Field(default=None, max_length=20, description="동 (예: 129)")
    asking_price: int = Field(gt=0, description="매물 호가 (만원)")
    supply_area: float | None = Field(default=None, gt=0, description="공급면적 ㎡ (참고용)")
    label: str = ""
    memo: str | None = None


class ListingOut(BaseModel):
    id: int
    complex_id: int
    complex_name: str
    label: str
    exclusive_area: float
    supply_area: float | None
    exclusive_ratio: float | None
    floor: int | None
    asking_price: int
    asking_ppp: float
    memo: str | None
