"""Strict Vietnamese route grammar; unknown clauses reject the entire request."""
import re
import unicodedata


def normalize(text):
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", text).split())


class CommandParser:
    def __init__(self, regions):
        self.aliases = {}
        for region in regions:
            ident = region["id"]
            for alias in [ident, region["name"], f"khu vực {ident}", f"phòng {ident}", *region.get("aliases", [])]:
                key = normalize(alias)
                if not key or (key in self.aliases and self.aliases[key] != ident):
                    raise ValueError(f"Tên vùng mơ hồ: {alias}")
                self.aliases[key] = ident

    def parse(self, text):
        text = normalize(text)
        if text in {"dung", "dung lai", "huy", "huy lenh"}:
            return []
        text = re.sub(r"^(?:robot |hay |vui long )+", "", text)
        match = re.fullmatch(r"(?:di chuyen|di|den)\s+(.+)", text)
        if not match:
            raise ValueError("Chưa hiểu lệnh. Hãy nói: Đi đến khu vực A")
        body = match[1]
        # `đến A` is also a complete imperative.
        if text.startswith("den "):
            body = "den " + body
        if body.startswith("tu "):
            body = body[3:]
            if " den " not in body:
                raise ValueError("Lệnh từ A cần có đích đến")
        elif body.startswith("den "):
            body = body[4:]
        else:
            raise ValueError("Cần 'đi đến ...' hoặc 'di chuyển từ ... đến ...'")
        parts = re.split(r"\s+(?:roi den|roi|qua|den)\s+", body)
        route = []
        for part in parts:
            if part not in self.aliases:
                raise ValueError(f"Khu vực không tồn tại hoặc tên chưa rõ: {part}")
            route.append(self.aliases[part])
        if len(route) > 10:
            raise ValueError("Tối đa 10 điểm trong một lệnh")
        return route
