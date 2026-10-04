import { useEffect, useState } from 'react'

import { api, STATIC_MODE } from '../api'
import Loading from './Loading'

/**
 * 적합을 기다리는 화면(시장 분석·지도·분해 모델)의 로딩 표시.
 *
 * ## 왜 문구가 하나면 안 되나
 *
 * 처음에는 어느 경우든 "모델을 적합하는 중" 이라고 적었는데, 그건 대부분의 경우
 * **사실이 아니다.** 적합은 한 번만 계산하고 데이터와 코드가 그대로면 다시 쓴다.
 * 그러니 실제로 일어나는 일은 셋 중 하나다.
 *
 * | 상태 | 실제로 하는 일 | 걸리는 시간 |
 * |---|---|---|
 * | 캐시 없음 | 11만 건으로 **회귀를 계산** | 수십 초 |
 * | 디스크에 있음 | 저장해 둔 결과를 **읽어 온다** | 2초 안팎 |
 * | 메모리에 있음 | 그대로 쓴다 | 표시 자체가 안 뜬다 |
 *
 * 걸리는 시간이 한 자릿수 다르고 사용자가 할 일도 다르다 — 앞은 기다려야 하고
 * 뒤는 곧 끝난다. 그런데 "적합하는 중" 이라고만 적으면 2초짜리도 수십 초처럼
 * 보이고, 반대로 수십 초짜리에 아무 설명이 없으면 멈춘 줄 안다.
 *
 * ## 짐작하지 않고 물어본다
 *
 * 경과 시간으로 짐작할 수도 있다(2초를 넘겼으면 계산 중이겠지). 하지만 그건 이미
 * 기다린 뒤에야 아는 것이고, 처음 몇 초 동안은 틀린 문구를 보여 주게 된다.
 * `/api/model/status` 가 12ms 에 답하므로 그냥 물어본다.
 */
export default function FitLoading({ months, what = '모델' }) {
  const [source, setSource] = useState(undefined) // undefined = 아직 모름

  useEffect(() => {
    let alive = true
    setSource(undefined)
    if (STATIC_MODE) return
    api
      .modelStatus({ months })
      .then((d) => alive && setSource(d.source ?? null))
      .catch(() => alive && setSource(undefined))
    return () => {
      alive = false
    }
  }, [months])

  // 정적 사이트에서는 적합이 일어나지 않는다 — 내보낸 파일을 읽을 뿐이다.
  // 여기서 '계산하는 중' 이라고 적으면 일어나지 않는 일을 적는 셈이다.
  if (STATIC_MODE) return <Loading label={`${what} 불러오는 중`} />

  if (source === null) {
    return (
      <Loading
        label={`${what} 계산하는 중`}
        slowAfter={4}
        hint={
          '이 기간의 적합이 아직 없어 지금 계산합니다 — 실거래 11만 건, 단지 2천 곳으로 ' +
          '회귀를 돌립니다. 한 번 끝내면 결과를 저장해 두므로, 다음부터는 이 탭도 ' +
          '다른 탭도 바로 열립니다(서버를 다시 띄워도 그대로입니다).'
        }
      />
    )
  }

  if (source === 'disk') {
    return (
      <Loading
        label={`저장해 둔 ${what} 불러오는 중`}
        slowAfter={8}
        hint="저장된 적합을 읽는 중입니다. 보통 2초 안팎이며, 읽고 나면 이후로는 바로 열립니다."
      />
    )
  }

  // 상태를 아직 모르거나(첫 12ms) 조회에 실패한 경우 — 단정하지 않는다.
  return <Loading label={`${what} 준비하는 중`} />
}
