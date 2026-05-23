from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ChannelConfig:
    """A single YouTube channel entry from channels.yaml."""

    channel_id: str  # internal identifier (e.g. 'liam-ottley')
    handle: str      # YouTube handle (e.g. '@liamottley')
    display_name: str


@dataclass(slots=True)
class AppConfig:
    """Top-level runtime configuration: video fetch limit and target channel list."""

    default_video_limit: int
    channels: list[ChannelConfig]


def load_config(path: Path) -> AppConfig:
    lines = path.read_text(encoding="utf-8").splitlines()
    default_video_limit = 10
    channels: list[ChannelConfig] = []
    current: dict[str, str] | None = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("default_video_limit:"):
            default_video_limit = int(line.split(":", 1)[1].strip())
            continue
        if line.startswith("- "):
            if current:
                try:
                    channels.append(
                        ChannelConfig(
                            channel_id=current["channel_id"],
                            handle=current["handle"],
                            display_name=current["display_name"],
                        )
                    )
                except KeyError as exc:
                    raise ValueError(
                        f"Channel entry in {path} is missing required field {exc}. "
                        f"Each channel must have channel_id, handle, and display_name."
                    ) from exc
            current = {}
            line = line[2:]
        if ":" in line and current is not None:
            key, value = line.split(":", 1)
            current[key.strip()] = value.strip().strip('"')

    if current:
        try:
            channels.append(
                ChannelConfig(
                    channel_id=current["channel_id"],
                    handle=current["handle"],
                    display_name=current["display_name"],
                )
            )
        except KeyError as exc:
            raise ValueError(
                f"Channel entry in {path} is missing required field {exc}. "
                f"Each channel must have channel_id, handle, and display_name."
            ) from exc

    if not channels:
        raise ValueError(f"No channels defined in config: {path}")
    return AppConfig(default_video_limit=default_video_limit, channels=channels)
