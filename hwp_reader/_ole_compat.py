"""일부 한컴 생성 CFB의 비표준 할당표를 제한적으로 읽는 호환 리더.

정상 입력은 항상 `_ole.OleFile`이 먼저 처리한다. 이 클래스는 strict 리더가
거부한 뒤에만 사용하며, 시그니처·섹터 크기·범위·DIFAT 순환·stream 크기 같은
안전 불변식은 그대로 유지하고 FAT 표식/중복처럼 실제 문서에서 관찰되는
할당표 비정합만 완화한다.

동작 설계 교차검증: edwardkim/rhwp LenientCfbReader (MIT).
"""

import struct

from ._ole import DIFSECT, ENDOFCHAIN, FATSECT, FREESECT, NOSTREAM, OleFile


class CompatOleFile(OleFile):
    """strict CFB 실패 후에만 쓰는 제한적 호환 리더."""

    def __init__(self, path_or_bytes):
        self.compat_warnings = []
        super().__init__(path_or_bytes)

    def _read_fat(self):
        """DIFAT의 중복 FAT SID와 잘못된 자체 표식만 제한적으로 허용한다."""
        raw_ids = [sid for sid in self._header_difat if sid != FREESECT]
        next_difat = self._first_difat_sector
        seen_difat = set()
        entries_per_sector = self.sector_size // 4

        while len(raw_ids) < self._num_fat_sectors:
            if self._num_difat_sectors == 0 or next_difat in (FREESECT, ENDOFCHAIN):
                break
            if next_difat in seen_difat:
                self._bad("호환 모드에서도 DIFAT 체인 순환은 허용하지 않는다")
            if len(seen_difat) >= self._num_difat_sectors:
                self._bad("DIFAT 섹터 수가 헤더와 다르다")
            seen_difat.add(next_difat)
            block = self._read_sector(next_difat)
            values = struct.unpack("<{}I".format(entries_per_sector), block)
            raw_ids.extend(sid for sid in values[:-1] if sid != FREESECT)
            next_difat = values[-1]

        unique = []
        seen = set()
        for sid in raw_ids[:self._num_fat_sectors]:
            if sid in (FREESECT, ENDOFCHAIN, FATSECT, DIFSECT, NOSTREAM):
                continue
            if not isinstance(sid, int) or sid < 0 or sid >= self._sector_count:
                self._bad("호환 FAT 섹터 번호가 파일 범위를 벗어났다")
            if sid in seen:
                self.compat_warnings.append("DIFAT의 중복 FAT 섹터 참조를 한 번만 사용했다")
                continue
            seen.add(sid)
            unique.append(sid)

        if not unique:
            self._bad("호환 모드에서도 읽을 FAT 섹터가 없다")
        if len(unique) > self._sector_count:
            self._bad("호환 FAT 섹터 수가 전체 섹터 수를 넘는다")

        fat = []
        for sid in unique:
            fat.extend(struct.unpack(
                "<{}I".format(entries_per_sector), self._read_sector(sid)
            ))

        for sid in unique:
            if sid >= len(fat):
                self._bad("FAT 테이블이 FAT 섹터 자체를 포함하지 못한다")
            if fat[sid] != FATSECT:
                self.compat_warnings.append("FAT 섹터의 FATSECT 표식 불일치를 허용했다")
        for sid in seen_difat:
            if sid >= len(fat):
                self._bad("FAT 테이블이 DIFAT 섹터 자체를 포함하지 못한다")
            if fat[sid] != DIFSECT:
                self.compat_warnings.append("DIFAT 섹터의 DIFSECT 표식 불일치를 허용했다")
        return fat

    def _chain(self, start, table, needed=None, what="FAT"):
        """선언 stream 크기 이후의 불필요한 FAT 꼬리만 잘라낸다.

        필요한 구간 내부의 순환·예약값·범위 오류는 strict와 동일하게 실패한다.
        """
        if needed == 0:
            return []
        if start in (FREESECT, ENDOFCHAIN, NOSTREAM):
            self._bad(f"{what} 체인의 시작 섹터가 없다")
        if needed is not None and needed > len(table):
            self._bad(f"{what} 체인이 가질 수 있는 섹터 수를 넘는다")

        out = []
        seen = set()
        sector = start
        while True:
            if sector in seen:
                self._bad(f"{what} 체인이 순환한다")
            if not isinstance(sector, int) or sector < 0 or sector >= len(table):
                self._bad(f"{what} 체인의 섹터 번호가 범위를 벗어났다")
            seen.add(sector)
            out.append(sector)
            next_sector = table[sector]

            if needed is not None and len(out) >= needed:
                if next_sector != ENDOFCHAIN:
                    self.compat_warnings.append(f"{what} 체인의 선언 크기 이후 꼬리를 무시했다")
                return out
            if next_sector == ENDOFCHAIN:
                if needed is None:
                    return out
                self._bad(f"{what} 체인이 예상보다 짧다")
            if next_sector in (FREESECT, FATSECT, DIFSECT, NOSTREAM):
                self._bad(f"{what} 체인이 예약된 섹터를 가리킨다")
            sector = next_sector
