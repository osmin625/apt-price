from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'apt.db'}"

    # 공공데이터포털 '아파트 매매 실거래가 상세 자료'(15126468) 활용신청 후 받는
    # 일반 인증키(Decoding). https://www.data.go.kr/data/15126468/openapi.do
    molit_service_key: str = ""
    molit_base_url: str = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev"

    # 카카오 개발자센터 REST API 키. https://developers.kakao.com
    # 단지 POI 수집(fetch_complexes)과 좌표·역 조회(geocode)에 쓴다.
    # 지도 렌더링용 JavaScript 키는 별개이며 frontend/.env.local 에 들어간다.
    kakao_rest_key: str = ""

    # SK open API 보행자 경로안내. https://openapi.sk.com
    # 없으면 직선거리×1.25 추정치로 자동 폴백하므로 개발이 막히지는 않는다.
    tmap_app_key: str = ""
    tmap_base_url: str = "https://apis.openapi.sk.com/tmap/routes/pedestrian"

    # 한국부동산원 부동산통계 Open API(R-ONE) 인증키.
    # data.go.kr 15134761 은 API 유형이 LINK 라 **MOLIT 키를 쓸 수 없다** — R-ONE 에서
    # 따로 발급받는다. 없으면 샘플 모드(5행 고정)로 동작해 적재는 안 되지만
    # scripts/probe_reb.py 의 코드 대조는 그대로 돈다.
    reb_service_key: str = ""

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
(BASE_DIR / "data").mkdir(exist_ok=True)
