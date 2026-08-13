# Contributing

AI HWP Reader의 우선순위는 기능 수보다 AI에게 잘못된 문서 구조를 정상처럼 넘기지 않는 것입니다.

- 읽기 전용을 유지합니다.
- 실제 회사·고객·기관 문서를 저장소에 올리지 않습니다.
- `SKILL.md`와 `skill/hwp_reader_single.py`는 직접 수정하지 않고 `python tools/build_single.py`로 생성합니다.
- 신규 파서 동작에는 합성 fixture 기반 회귀시험을 추가합니다.

```bash
python -m pip install -e ".[dev]"
python -m pytest tests -q
python tools/build_single.py
git diff --exit-code -- SKILL.md skill/hwp_reader_single.py
```
