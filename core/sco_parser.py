from typing import Any

def _try_numeric(value: str) -> Any:
    v = value.strip()
    try: return int(v)
    except ValueError: pass
    try: return float(v)
    except ValueError: pass
    return v

def _fmt_value(raw_original: str, new_value: Any) -> str:
    leading = " " if raw_original.startswith(" ") else ""
    if isinstance(new_value, float): return f"{leading}{new_value:.6g}"
    if isinstance(new_value, int): return f"{leading}{new_value}"
    return str(new_value)

class KVTable:
    def __init__(self, raw_lines: list[str]):
        self.params: dict[str, Any] = {}
        self.param_order: list[str] = []
        self._raw_values: dict[str, str] = {}
        self._param_line: dict[str, int] = {}
        self._raw_lines: list[str] = list(raw_lines)
        self._dirty: set[str] = set()
        self._parse()

    def _parse(self):
        for line_idx, line in enumerate(self._raw_lines):
            tokens = line.split("\t")
            i = 0
            while i < len(tokens):
                key = tokens[i].strip()
                i += 1
                if key == "": continue
                raw_val = tokens[i] if i < len(tokens) else ""
                i += 1
                value = _try_numeric(raw_val) if raw_val.strip() != "" else raw_val.strip()
                if key not in self.params: self.param_order.append(key)
                self.params[key] = value
                self._raw_values[key] = raw_val
                self._param_line[key] = line_idx

    def set(self, param: str, value: Any) -> bool:
        if param not in self.params: return False
        self.params[param] = value
        self._dirty.add(param)
        return True

    def to_lines(self) -> list[str]:
        dirty_idxs = {self._param_line[p] for p in self._dirty if p in self._param_line}
        out: list[str] = []
        for idx, raw_line in enumerate(self._raw_lines):
            if idx not in dirty_idxs:
                out.append(raw_line)
            else:
                tokens = raw_line.split("\t")
                i = 0
                new_tokens: list[str] = []
                while i < len(tokens):
                    key = tokens[i].strip()
                    if key == "" or i + 1 >= len(tokens):
                        new_tokens.append(tokens[i])
                        i += 1
                        continue
                    raw_val = tokens[i + 1]
                    new_tokens.append(tokens[i])
                    new_tokens.append(_fmt_value(raw_val, self.params[key]) if key in self._dirty else raw_val)
                    i += 2
                out.append("\t".join(new_tokens))
        return out

class TabularTable:
    def __init__(self, raw_lines: list[str]):
        self._raw_lines: list[str] = list(raw_lines)
        self._raw_header: str = ""
        self._raw_rows: list[str] = []
        self.columns: list[str] = []
        self.rows: list[dict[str, Any]] = []
        self._dirty: bool = False
        self._parse()

    def _parse(self):
        if not self._raw_lines: return
        self._raw_header = self._raw_lines[0]
        self.columns = [c.strip() for c in self._raw_header.split("\t")]
        for line in self._raw_lines[1:]:
            if not line.strip(): continue
            self._raw_rows.append(line)
            values = [_try_numeric(v) for v in line.split("\t")]
            while len(values) < len(self.columns): values.append("")
            self.rows.append(dict(zip(self.columns, values)))

    def set_rows(self, new_rows: list[dict[str, Any]]):
        self.rows = list(new_rows)
        self._dirty = True

    def to_lines(self) -> list[str]:
        out = [self._raw_header]
        if not self._dirty:
            out.extend(self._raw_rows)
        else:
            for row in self.rows:
                cells = [str(row.get(col, "")) for col in self.columns]
                out.append("\t".join(cells))
        return out

_TABULAR_OBJECTS: frozenset[str] = frozenset({
    "S-CONCRETE Customized Bar Information", "S-CONCRETE Panel Information",
    "S-CONCRETE Zone Information", "S-CONCRETE Sectional Loads", "S-CONCRETE Panel Loads",
})

class ScoObject:
    def __init__(self, name: str, obj_line: str, table_line: str, data_lines: list[str]):
        self.name = name
        self._obj_line = obj_line
        self._table_line = table_line
        self.table: KVTable | TabularTable = TabularTable(data_lines) if name in _TABULAR_OBJECTS else KVTable(data_lines)

    @property
    def is_kv(self) -> bool: return isinstance(self.table, KVTable)
    @property
    def is_tabular(self) -> bool: return isinstance(self.table, TabularTable)

    def to_lines(self) -> list[str]:
        return [self._obj_line, self._table_line] + self.table.to_lines() + ["@EndTable@"]

class ScoFile:
    def __init__(self, raw_text: str):
        self._preamble_lines: list[str] = []
        self.objects: list[ScoObject] = []
        self._load(raw_text)

    def _load(self, raw_text: str):
        lines = raw_text.splitlines(keepends=False)
        current_name, current_obj_line, current_table_line = "", "", ""
        current_data: list[str] = []
        in_table, seen_object = False, False

        for line in lines:
            s = line.strip()
            if s.startswith("@Object@"):
                seen_object = True
                parts = s.split("@")
                current_name = parts[2].strip() if len(parts) > 2 else s
                current_obj_line = line
                current_table_line = ""
                current_data = []
                in_table = False
            elif s.startswith("@Table@"):
                current_table_line = line
                in_table = True
            elif s == "@EndTable@":
                self.objects.append(ScoObject(current_name, current_obj_line, current_table_line, current_data))
                current_data = []
                in_table = False
            elif in_table:
                current_data.append(line)
            elif not seen_object:
                self._preamble_lines.append(line)

    def get_object(self, name: str) -> ScoObject | None:
        nl = name.lower()
        for obj in self.objects:
            if nl in obj.name.lower(): return obj
        return None

    @property
    def sectional_loads(self) -> TabularTable | None:
        obj = self.get_object("Sectional Loads")
        return obj.table if (obj and obj.is_tabular) else None

    def _kv_objects(self) -> list[ScoObject]: return [o for o in self.objects if o.is_kv]

    def set_params(self, updates: dict[str, Any]) -> dict[str, bool]:
        results = {}
        for k, v in updates.items():
            success = False
            for obj in self._kv_objects():
                if obj.table.set(k, v):
                    success = True
                    break
            results[k] = success
        return results

    def _serialise(self) -> str:
        all_lines: list[str] = list(self._preamble_lines)
        for obj in self.objects: all_lines.extend(obj.to_lines())
        return "\r\n".join(all_lines) + "\r\n"