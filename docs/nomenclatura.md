# Nomenclatura ItaTorrents

Convenzioni di denominazione ufficiali ItaTorrents. `unit3dprep` costruisce i nomi secondo queste regole a partire da `guessit` + `pymediainfo` + TMDB.

!!! note "Fonte"
    Contenuto derivato da `itatorrents-nomenclatura.md` nel repo. Aggiornamenti ufficiali da [ItaTorrents](https://itatorrents.xyz).

---

## Introduzione

Nell'interesse di una ricerca efficiente e della coerenza del sito, ItaTorrents ha rigide convenzioni di denominazione. Si prega di nominare il torrent in loco utilizzando il seguente standard.

---

## Struttura titolo — Full Disc, Remux

```
Name  Year  S##E##  Cut  REPACK  Resolution  Edition  Region  3D  SOURCE  TYPE  Hi10P  HDR  VCodec  Dub  ACodec  Channels  Object-Tag
```

## Struttura titolo — Encode, WEB-DL, WEBRip, HDTV, DLMux, BDMux, WEBMux, DVDMux, BDRip, DVDRip

```
Name  Year  S##E##  Cut  REPACK  Resolution  Edition  3D  SOURCE  TYPE  Dub  ACodec  Channels  Object  Hi10P  HDR  VCodec-Tag
```

---

## Dettaglio dei campi

- **Name** — nome del titolo riconosciuto a livello internazionale (solitamente reperibile su TMDB, a meno che non sia errato). Devono essere inclusi tutti i segni di punteggiatura, inclusi due punti, apostrofi e virgole.
- **Year** — anno di uscita secondo TMDB. I contenuti TV includono l'anno solo se esistono più serie con lo stesso nome.
- **S##E##** — stagione e numero dell'episodio, se applicabile.
    - Singolo episodio: `S##E##`.
    - Doppio episodio: `S##E##E##`.
    - Più episodi di una stagione non ancora conclusa: `S##E##-##`.
    - Extras: `S## Extras`.
- **Cut** — se omesso, si presume teatrale. Altrimenti: `Director's Cut`, `Extended`, `Special Edition`, `Unrated`, `Uncut`, `Super Duper Cut`.
- **Resolution** — `480i`, `480p`, `576i`, `576p`, `720p`, `1080i`, `1080p`, `2160p`, `4320p`.
- **Edition** — `XXth Anniversary Edition`, `Remastered`, `4K Remaster`, `Criterion Collection`, `Limited`. **Ometti dal nome** e inserisci nella descrizione. I dischi possono includere il distributore (es. `Criterion Collection`). FanRes richiede il processo usato nel restauro (`DNR`, `RECONSTRUCTED`, `RECUT`, `REEDIT`, `REGRADE`, `RESCAN`, `RESTORED`, `UPSCALED`). Il nome del FanRes è incluso nel `Cut`.
- **Region** — codice di 3 lettere del paese di uscita del disco. **Solo per dischi**.
- **Source** — sorgente video:
    - Dischi: `NTSC DVD5`, `NTSC DVD9`, `PAL DVD5`, `PAL DVD9`, `HD DVD`, `Blu-ray`, `3D Blu-ray`, `UHD Blu-ray`.
    - Remux/Encode: `NTSC DVD`, `PAL DVD`, `HDDVD`, `3D BluRay`, `BluRay`, `UHD BluRay`.
    - WEB-DL / WEBRip: abbreviazione del provider streaming.
    - HDTV: `HDTV` o `UHDTV`.
- **Type** — omesso per Full Disc, Encode, HDTV. Altrimenti: `REMUX`, `WEB-DL`, `WEBRip`.
- **HDR** — se omesso si presume SDR. Altrimenti: `HDR`, `HDR10+`, `DV HDR`, `DV`, `DV HDR10+`, `HLG`, `PQ10`.
- **Hi10P** — profondità di bit SDR di 10 bit AVC/H.264/x264.
- **VCodec** — codec video. **Omettere per DVD**.
    - Full Disc / Remux: `MPEG-2`, `VC-1`, `AVC`, `HEVC`.
    - WEB-DL / HDTV non modificata: `H.264`, `H.265`, `VP9`, `MPEG-2`.
    - Encode / WEBRip / HDTV codificata: `x264`, `x265`.
- **Dub** — una o più tracce audio (`ITA`, `ENG`, `SPA`, `GER`, `KOR`, ...): includere qualsiasi traccia audio presente.
- **ACodec** — `DD`, `DD EX`, `DD+`, `DD+ EX`, `TrueHD`, `DTS`, `DTS-ES`, `DTS-HD MA`, `DTS-HD HRA`, `DTS:X`, `LPCM`, `FLAC`, `ALAC`, `AAC`, `Opus` — codec audio della traccia predefinita.
- **Channels** — `1.0`, `2.0`, `4.0`, `5.1`, `6.1`, `7.1`, `9.1`, `11.1` — canali della migliore traccia audio.
- **Object** — se omesso si presume nessuno. Altrimenti: `Atmos`, `Auro3D`.
- **Tag** — `UserName` / `ReleaseGroup` — tag del gruppo di rilascio.
