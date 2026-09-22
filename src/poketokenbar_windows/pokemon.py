from __future__ import annotations

import json
import random
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EGG_HATCH_THRESHOLD = 5_000_000
GRADUATION_TOTALS = {
    "common": 750_000_000,
    "uncommon": 1_875_000_000,
    "rare": 3_000_000_000,
    "legendary": 6_000_000_000,
}
RARE_CANDY_XP = 100_000_000
RARE_CANDY_PRICE = 500_000_000
MINT_PRICE = 100_000_000
SHINY_CHARM_PRICE = 3_000_000_000
FRESH_EGG_PRICE = 1_000_000_000
SHINY_DENOMINATOR = 64
SHINY_CHARM_DENOMINATOR = 48
DITTO_SPECIES_ID = 132

NATURES = [
    "Hardy", "Lonely", "Brave", "Adamant", "Naughty",
    "Bold", "Docile", "Relaxed", "Impish", "Lax",
    "Timid", "Hasty", "Serious", "Jolly", "Naive",
    "Modest", "Mild", "Quiet", "Bashful", "Rash",
    "Calm", "Gentle", "Sassy", "Careful", "Quirky",
]

RARITY_RANK = {"common": 0, "uncommon": 1, "rare": 2, "legendary": 3}


def rarity_from(capture_rate: int, is_legendary: bool, is_mythical: bool) -> str:
    if is_legendary or is_mythical:
        return "legendary"
    if capture_rate <= 45:
        return "rare"
    if capture_rate <= 120:
        return "uncommon"
    return "common"


def phase_threshold(rarity: str, total_forms: int, stage_index: int, growth_multiplier: int = 1) -> int:
    k = max(1, total_forms)
    i = stage_index + 1
    denominator = k * (k + 1) / 2.0
    standard = round(GRADUATION_TOTALS[rarity] * i / denominator)
    return max(1, round(standard / max(1, growth_multiplier)))


def egg_price(tier: str | None = None) -> int:
    if tier is None:
        return FRESH_EGG_PRICE
    return round(FRESH_EGG_PRICE * GRADUATION_TOTALS[tier] / GRADUATION_TOTALS["common"])


def _species_id(url_or_name: Any) -> int | None:
    if isinstance(url_or_name, dict):
        url_or_name = url_or_name.get("url")
    if not isinstance(url_or_name, str):
        return None
    match = re.search(r"/pokemon-species/(\d+)/?", url_or_name)
    return int(match.group(1)) if match else None


@dataclass(slots=True)
class HatchResult:
    base_id: int
    path_ids: list[int]
    rarity: str
    nature: str
    is_shiny: bool
    capture_rate: int


class PokeAPIClient:
    def __init__(self, cache_dir: Path, timeout: float = 12.0):
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.json_dir = cache_dir / "api"
        self.sprite_dir = cache_dir / "sprites"
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.sprite_dir.mkdir(parents=True, exist_ok=True)

    def _json(self, url: str, cache_key: str) -> dict[str, Any]:
        path = self.json_dir / f"{cache_key}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except (OSError, json.JSONDecodeError):
                pass
        request = urllib.request.Request(url, headers={"User-Agent": "PokeTokenBar-Windows/0.1", "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = json.load(response)
        if not isinstance(data, dict):
            raise ValueError("PokéAPI returned a non-object response")  # noqa: TRY004
        try:
            path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        except OSError:
            pass
        return data

    def species(self, species_id: int) -> dict[str, Any]:
        return self._json(f"https://pokeapi.co/api/v2/pokemon-species/{species_id}", f"species-{species_id}")

    def evolution_chain(self, chain_url: str) -> dict[str, Any]:
        match = re.search(r"/evolution-chain/(\d+)/?", chain_url)
        key = f"evolution-{match.group(1) if match else abs(hash(chain_url))}"
        return self._json(chain_url, key)

    def localized_name(self, species_id: int, language: str = "en") -> str:
        try:
            data = self.species(species_id)
        except Exception:  # noqa: BLE001
            return f"#{species_id}"
        names = data.get("names") if isinstance(data.get("names"), list) else []
        preferred = [language]
        if language == "ja":
            preferred = ["ja-Hrkt", "ja"]
        preferred.append("en")
        for code in preferred:
            for item in names:
                if not isinstance(item, dict):
                    continue
                lang = item.get("language")
                if isinstance(lang, dict) and lang.get("name") == code and isinstance(item.get("name"), str):
                    return item["name"]
        return str(data.get("name") or f"#{species_id}").replace("-", " ").title()

    def _random_path(self, node: dict[str, Any]) -> list[int]:
        species_id = _species_id(node.get("species"))
        if species_id is None or species_id > 649:
            return []
        children = [c for c in node.get("evolves_to", []) if isinstance(c, dict)]
        supported = [c for c in children if (_species_id(c.get("species")) or 9999) <= 649]
        if not supported:
            return [species_id]
        child = random.choice(supported)
        suffix = self._random_path(child)
        return [species_id] + suffix

    def hatch(self, minimum_rarity: str | None = None, shiny_charm: bool = False, max_attempts: int = 1200) -> HatchResult:
        minimum_rank = RARITY_RANK.get(minimum_rarity or "common", 0)
        last_error: Exception | None = None
        for _ in range(max_attempts):
            species_id = random.randint(1, 649)
            if species_id == DITTO_SPECIES_ID:
                continue
            try:
                species = self.species(species_id)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
            if species.get("evolves_from_species") is not None:
                continue
            capture_rate = int(species.get("capture_rate") or 0)
            rarity = rarity_from(capture_rate, bool(species.get("is_legendary")), bool(species.get("is_mythical")))
            if RARITY_RANK[rarity] < minimum_rank:
                continue
            # Upstream weights hatches by official capture rate. Rejection sampling
            # gives each base species probability proportional to capture_rate.
            if random.randint(1, 255) > max(1, min(255, capture_rate)):
                continue
            chain_ref = species.get("evolution_chain")
            if not isinstance(chain_ref, dict) or not isinstance(chain_ref.get("url"), str):
                continue
            try:
                chain = self.evolution_chain(chain_ref["url"])
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
            root = chain.get("chain")
            if not isinstance(root, dict):
                continue
            path = self._random_path(root)
            if not path or path[0] != species_id:
                continue
            denominator = SHINY_CHARM_DENOMINATOR if shiny_charm else SHINY_DENOMINATOR
            return HatchResult(
                base_id=species_id,
                path_ids=path,
                rarity=rarity,
                nature=random.choice(NATURES),
                is_shiny=random.randrange(denominator) == 0,
                capture_rate=capture_rate,
            )
        if last_error:
            raise RuntimeError(f"Could not hatch a Pokemon: {last_error}")
        raise RuntimeError("Could not find an eligible Pokemon hatch candidate")

    def sprite_path(self, species_id: int, shiny: bool = False, animated: bool = True) -> Path | None:
        variant = "shiny-" if shiny else ""
        suffix = "gif" if animated else "png"
        path = self.sprite_dir / f"{species_id}-{variant}{'animated' if animated else 'static'}.{suffix}"
        if path.exists() and path.stat().st_size > 0:
            return path
        if animated:
            middle = "animated/shiny" if shiny else "animated"
            url = (
                "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/"
                f"versions/generation-v/black-white/{middle}/{species_id}.gif"
            )
        else:
            middle = "shiny/" if shiny else ""
            url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{middle}{species_id}.png"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "PokeTokenBar-Windows/0.1"})
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                blob = response.read()
            if not blob:
                return None
            path.write_bytes(blob)
            return path
        except (OSError, urllib.error.URLError, TimeoutError):
            if animated:
                return self.sprite_path(species_id, shiny=shiny, animated=False)
            return None

    def egg_sprite_path(self) -> Path | None:
        path = self.sprite_dir / "egg-static.png"
        if path.exists() and path.stat().st_size > 0:
            return path
        url = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/egg.png"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "PokeTokenBar-Windows/0.1"})
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                blob = response.read()
            if not blob:
                return None
            path.write_bytes(blob)
            return path
        except (OSError, urllib.error.URLError, TimeoutError):
            return None

    def item_sprite_path(self, item_name: str) -> Path | None:
        """Fetch a static PokeAPI item sprite without bundling third-party art."""
        normalized = item_name.strip().lower()
        if not re.fullmatch(r"[a-z0-9-]+", normalized):
            raise ValueError("Invalid PokeAPI item name")
        path = self.sprite_dir / f"item-{normalized}.png"
        if path.exists() and path.stat().st_size > 0:
            return path
        url = (
            "https://raw.githubusercontent.com/PokeAPI/sprites/master/"
            f"sprites/items/{normalized}.png"
        )
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "PokeTokenBar-Windows/0.1"},
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                blob = response.read()
            if not blob:
                return None
            path.write_bytes(blob)
            return path
        except (OSError, urllib.error.URLError, TimeoutError):
            return None
