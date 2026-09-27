# 경기 남부 아파트 적정 시세

국토교통부 실거래가를 기반으로 아파트 매물의 적정 시세를 산출하는 웹 서비스.
대상은 **수원 생활권**(수원·용인·화성·안양·오산·의왕·군포·과천, 17개 시군구)의
아파트 매매다. 수원 4개 구로 시작해 인접 시로 넓혔다 — 요인별 보정계수를 더 촘촘히
보려면 요인이 실제로 변해야 하는데, 한 도시 안에서는 강남 접근성이 30~65분 구간에
몰려 있어 곡선의 양 끝이 식별되지 않았다.

## 문서

한 파일에 다 넣으면 필요 없는 부분까지 읽게 된다. 목적별로 나눠 두었다.

| 문서 | 무엇이 있나 | 언제 보나 |
|---|---|---|
| [docs/design.md](docs/design.md) | 화면·기능 설계 결정, 왜 그렇게 만들었나 | 동작을 바꾸기 전에 |
| [docs/model.md](docs/model.md) | 2단계 헤도닉 회귀와 비교표본 방식의 수식 | 숫자가 어떻게 나오는지 알아야 할 때 |
| [docs/data.md](docs/data.md) | 공공 API 적재, 파싱 함정, 대상 지역 넓히기 | 데이터를 채우거나 지역을 늘릴 때 |
| [docs/architecture.md](docs/architecture.md) | 어느 파일이 무엇을 맡는지 | 코드를 처음 열 때 |
| [docs/performance.md](docs/performance.md) | 느린 곳을 찾아 고친 기록 | 다시 느려졌을 때 |

## 실행

```bash
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
cp .env.example .env          # 키를 채운다 — docs/data.md 참조
python -m scripts.migrate     # 스키마
python -m uvicorn app.main:app --reload

cd ../frontend && npm install && npm run dev
```

데이터를 채우는 순서(실거래 → 좌표 → 역 → 도보 → 세대수)와 키 발급은
[docs/data.md](docs/data.md) 에 있다. 키가 없어도 막히지는 않는다 — TMap 키가 없으면
도보거리는 직선×1.25 추정치로, 카카오 키가 없으면 단지에 저장된 역거리로 폴백한다.

## 휴대폰에서 보기

화면은 좁은 폭에 맞춰 뒀다. 탭은 줄바꿈 대신 가로로 밀리고, 표는 열을 줄이지 않고
가로 스크롤한다 — 열을 빼면 비교가 안 되기 때문이다.

### 같은 Wi-Fi (권장)

```bash
cd frontend && npm run dev:lan      # vite --host
```

휴대폰에서 `http://<PC의 LAN IP>:5173` 으로 연다. IP 확인:

```bash
powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' } | Select-Object IPAddress, InterfaceAlias"
```

기본 `npm run dev` 는 localhost 만 듣는다. 이 앱에는 로그인이 없고 백엔드 키가
`.env` 에 있으므로 **필요할 때만** 연다.

처음 한 번은 두 가지를 더 해야 한다.

1. **윈도우 방화벽**에서 5173 인바운드를 허용한다. 관리자 PowerShell:

   ```powershell
   New-NetFirewallRule -DisplayName "apt-price dev 5173" -Direction Inbound -LocalPort 5173 -Protocol TCP -Action Allow -Profile Private
   ```

   `-Profile Private` 를 붙여 집 네트워크에서만 열리게 한다. 다 쓰면
   `Remove-NetFirewallRule -DisplayName "apt-price dev 5173"` 로 지운다.

2. **카카오 개발자센터 > 내 애플리케이션 > 플랫폼 > Web** 에
   `http://<LAN IP>:5173` 을 등록한다. 카카오는 origin 을 완전일치로 검사하므로
   등록하지 않으면 **지도 탭만** 설정 안내로 바뀐다(나머지 탭은 정상).

백엔드는 건드릴 것이 없다. 휴대폰은 Vite 에만 붙고, `/api` 는 Vite 가 서버 쪽에서
백엔드로 넘기므로 CORS 도 타지 않는다.

### 집 밖에서도 보려면

셋 다 무료 플랜이 있지만 성격이 다르다(2026-09 확인).

| | 무료 범위 | 노출 | 걸리는 점 |
|---|---|---|---|
| **Tailscale** | Personal 무료(영구) · 6명 · 기기 무제한 | 내 기기끼리만 | 비상업용 한정. 회사 도메인 계정은 유료 체험으로 들어간다 |
| Cloudflare Quick Tunnel | 무료 · 계정·도메인 불필요 | **공개 URL** | 동시 요청 200개 초과 시 429 · 문서에 *테스트/개발용* 명시 |
| ngrok | 무료 · 월 1GB / 요청 2만 건 | **공개 URL** | 브라우저에 경고 중간 페이지 · 주소가 매번 바뀐다 |

**이 앱에는 로그인이 없다.** 공개 URL을 쓰면 붙여넣은 매물과 호가 기록이 링크를 아는
누구에게나 보인다. 실거래가 자체는 공공 데이터지만 그 점을 알고 쓸 것.

그래서 **Tailscale** 을 권한다. 공개되지 않고, 주소가 고정이라 카카오 origin 을 한 번만
등록하면 된다(터널 방식은 재시작할 때마다 주소가 바뀌어 매번 다시 등록해야 한다).

#### Tailscale 로 붙이기

1. **PC와 휴대폰에 각각 설치하고 같은 계정으로 로그인**한다.
   개인 이메일(Gmail 등)로 가입해야 무료 Personal 플랜이 붙는다.
   <https://tailscale.com/download>

2. **PC의 주소를 확인**한다. MagicDNS 이름을 쓰면 IP가 바뀌어도 그대로 쓸 수 있다.

   ```powershell
   tailscale status          # 맨 윗줄이 이 PC. 이름과 100.x.y.z 주소가 보인다
   tailscale ip -4           # 100.x.y.z 만
   ```

3. **개발 서버를 LAN 모드로 띄운다.** 같은 Wi-Fi 방식과 같은 명령이다 —
   `--host` 가 있어야 Tailscale 인터페이스에서도 듣는다.

   ```bash
   cd frontend && npm run dev:lan
   ```

4. **휴대폰에서** `http://<PC 이름>.<tailnet>.ts.net:5173` 으로 연다
   (또는 `http://100.x.y.z:5173`).

5. **카카오 개발자센터 > 플랫폼 > Web** 에 그 주소를 그대로 등록한다.
   안 하면 지도 탭만 설정 안내로 바뀐다.

안 붙으면 **방화벽 프로필**부터 본다. 위에서 만든 규칙은 `-Profile Private` 라,
Tailscale 어댑터가 Public 으로 분류돼 있으면 막힌다.

```powershell
Get-NetConnectionProfile    # Tailscale 어댑터의 NetworkCategory 확인
```

Private 이 아니면 그 어댑터만 Private 으로 바꾸거나
(`Set-NetConnectionProfile -InterfaceAlias "Tailscale" -NetworkCategory Private`),
규칙을 그 인터페이스에 한정해 다시 만든다.

#### Cloudflare Quick Tunnel (지금 한 번만 쓸 때)

```bash
cloudflared tunnel --url http://localhost:5173
```

가입도 도메인도 필요 없고 `*.trycloudflare.com` 주소가 즉시 나온다. 대신 **공개**이고,
껐다 켜면 주소가 바뀌어 카카오 origin 을 다시 등록해야 한다.

## 알려진 한계

- **매물 호가는 수동 입력**이다. 네이버부동산 등 호가 데이터는 공식 API가 없고 스크래핑은
  이용약관 위반 소지가 있어 PoC에서 제외했다. 대신 사용자가 **텍스트를 붙여넣으면**
  단지·면적·층·호가를 뽑아 채워 준다([설계 결정](docs/design.md) 참조).
  링크는 지원하지 않는다 —
  긁어오지 않겠다는 결정이기도 하고, 애초에 링크에 매물 정보가 들어 있지 않다.
- 단지 최고층이 실제 최고층이 아니라 관측 최고 거래층이므로, 거래가 적은 단지에서는
  "최상층" 판정이 부정확할 수 있다.
- 도보거리 정밀도에는 **살 수 없는 한계**가 있다. 카카오가 주는 단지 좌표는 중심점 하나인데
  한국 아파트 단지는 폭이 200~400m라 보행 출입구가 중심에서 300m 떨어질 수 있다. TMap 을
  써도 ±150m 는 남는다. TMap 의 가치는 정밀도가 아니라 **체계적 장벽**(경부선·원천리천·
  영동고속도로) 포착이다 — 분산이 아니라 편향 교정이라, R² 급등이 아니라 특정 단지가 크게
  움직이는 것을 기대해야 한다.
- `seed_stations.py` 의 **강남 소요시간은 수기 추정치**다. 공개된 대중교통 길찾기 REST API
  를 쓰지 않기 때문인데, 그래서 **강남접근성 계수만은 이 표만큼만 정확하다.** 다른 요인
  (면적·층·도보·연식·세대수·동 위치)은 실거래에서 직접 추정되므로 영향받지 않는다.
  표가 21개에서 67개로 커지며 세 종류의 오류가 드러났고 전부 검사로 잡아 냈다
  ([데이터 파이프라인](docs/data.md) 참조). 실측이 필요하면 ODsay 같은 길찾기 API 로
  이 표를 대체하면 된다.
- 강남 접근성은 구 고정효과와 상관이 높다. 신분당선 역(광교·상현)이 전부 영통구/이의동에
  몰려 있어 두 변수가 같은 것을 가리키는 구간이 있다. 계수는 보고하되 과신하면 안 된다.
- 요인 곡선을 얼마나 촘촘히 볼 수 있는지는 **표본이 정한다**. 지금은 단지 2,018곳이라
  매듭 7개를 쓰지만, 대상을 좁히면 자동으로 줄어든다(`hedonic.knots_for`).
- 동향·조망·리모델링 여부·학군 등 가격에 영향을 주는 다른 요인은 반영하지 않는다.
  모델 잔차에 이것들이 전부 섞여 있다. 결과는 참고용이며 투자 판단의 근거로 쓸 수 없다.
