# ItaTorrents naming convention

Official ItaTorrents naming conventions. `unit3dprep` builds filenames according to these rules from `guessit` + `pymediainfo` + TMDB.

!!! note "Source"
    Content derived from `itatorrents-nomenclatura.md` in the repo. Authoritative updates from [ItaTorrents](https://itatorrents.xyz).

---

## Introduction

For efficient search and site consistency, ItaTorrents enforces strict naming conventions. Please name torrents at the source using the following standard.

---

## Title structure — Full Disc, Remux

```
Name  Year  S##E##  Cut  REPACK  Resolution  Edition  Region  3D  SOURCE  TYPE  Hi10P  HDR  VCodec  Dub  ACodec  Channels  Object-Tag
```

## Title structure — Encode, WEB-DL, WEBRip, HDTV, DLMux, BDMux, WEBMux, DVDMux, BDRip, DVDRip

```
Name  Year  S##E##  Cut  REPACK  Resolution  Edition  3D  SOURCE  TYPE  Dub  ACodec  Channels  Object  Hi10P  HDR  VCodec-Tag
```

---

## Field reference

- **Name** — the internationally recognized title (usually taken from TMDB, unless wrong there). All punctuation must be preserved, including colons, apostrophes, and commas.
- **Year** — release year per TMDB. TV content includes the year only when multiple series share the same name.
- **S##E##** — season and episode number, where applicable.
    - Single episode: `S##E##`.
    - Double episode: `S##E##E##`.
    - Multiple episodes from an ongoing season: `S##E##-##`.
    - Extras: `S## Extras`.
- **Cut** — if omitted, assumed theatrical. Otherwise: `Director's Cut`, `Extended`, `Special Edition`, `Unrated`, `Uncut`, `Super Duper Cut`.
- **Resolution** — `480i`, `480p`, `576i`, `576p`, `720p`, `1080i`, `1080p`, `2160p`, `4320p`.
- **Edition** — `XXth Anniversary Edition`, `Remastered`, `4K Remaster`, `Criterion Collection`, `Limited`. **Omit from the name** and put it in the description. Discs may include the distributor (e.g. `Criterion Collection`). FanRes must include the restoration process (`DNR`, `RECONSTRUCTED`, `RECUT`, `REEDIT`, `REGRADE`, `RESCAN`, `RESTORED`, `UPSCALED`). The FanRes name belongs in `Cut`.
- **Region** — 3-letter country code of the disc release. **Discs only**.
- **Source** — video source:
    - Discs: `NTSC DVD5`, `NTSC DVD9`, `PAL DVD5`, `PAL DVD9`, `HD DVD`, `Blu-ray`, `3D Blu-ray`, `UHD Blu-ray`.
    - Remux / Encode: `NTSC DVD`, `PAL DVD`, `HDDVD`, `3D BluRay`, `BluRay`, `UHD BluRay`.
    - WEB-DL / WEBRip: streaming provider abbreviation.
    - HDTV: `HDTV` or `UHDTV`.
- **Type** — omitted for Full Disc, Encode, HDTV. Otherwise: `REMUX`, `WEB-DL`, `WEBRip`.
- **HDR** — if omitted, assumed SDR. Otherwise: `HDR`, `HDR10+`, `DV HDR`, `DV`, `DV HDR10+`, `HLG`, `PQ10`.
- **Hi10P** — SDR 10-bit depth for AVC/H.264/x264.
- **VCodec** — video codec. **Omit for DVDs**.
    - Full Disc / Remux: `MPEG-2`, `VC-1`, `AVC`, `HEVC`.
    - WEB-DL / unmodified HDTV: `H.264`, `H.265`, `VP9`, `MPEG-2`.
    - Encode / WEBRip / encoded HDTV: `x264`, `x265`.
- **Dub** — one or more audio tracks (`ITA`, `ENG`, `SPA`, `GER`, `KOR`, ...): include every track that is present.
- **ACodec** — `DD`, `DD EX`, `DD+`, `DD+ EX`, `TrueHD`, `DTS`, `DTS-ES`, `DTS-HD MA`, `DTS-HD HRA`, `DTS:X`, `LPCM`, `FLAC`, `ALAC`, `AAC`, `Opus` — audio codec of the default track.
- **Channels** — `1.0`, `2.0`, `4.0`, `5.1`, `6.1`, `7.1`, `9.1`, `11.1` — channels of the best audio track.
- **Object** — if omitted, assumed none. Otherwise: `Atmos`, `Auro3D`.
- **Tag** — `UserName` / `ReleaseGroup` — release group tag.
