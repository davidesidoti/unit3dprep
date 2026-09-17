# Nomenclatura ItaTorrents

Convenzioni di denominazione ufficiali ItaTorrents. `unit3dprep` costruisce i nomi secondo queste regole a partire da `guessit` + `pymediainfo` + TMDB.

!!! note "Fonte"
    Aggiornamenti ufficiali su [ItaTorrents](https://itatorrents.xyz). Il builder di nomi vive in `unit3dprep/core.py::build_name` e usa `extract_specs` (`pymediainfo`) + `guessit` + dati TMDB.

---

## Recupero dei tag originali

Per serie ed episodi, se Sonarr è configurato, il wizard cerca il rilascio scaricato
nella cronologia. Lo usa solo quando il file attuale corrisponde per percorso e
dimensione, l'importazione coincide con la data registrata e gli eventi di download
e importazione condividono episodio e ID download. Questo evita di riusare la
provenienza di una versione precedente dello stesso episodio. Il nome del rilascio
deve inoltre concordare con titolo, stagione e codec video. Il wizard mostra la
provenienza utilizzata; se Sonarr non risponde, continua con un avviso.

Un titolo interno che indica un codec incompatibile con il video reale (per esempio
`XviD` su un file HEVC) viene ignorato e segnalato. Senza una provenienza verificabile,
controlla manualmente la sorgente proposta: il filename può essere già errato.

Il nome della cartella stagione include i tag tecnici solo se tutti gli episodi
hanno profili concordanti e nessuna incoerenza irrisolta. Altrimenti viene proposto
solo titolo e stagione, con un avviso. Una selezione che comprende più stagioni
non riceve il numero della prima stagione.

In assenza di una provenienza Sonarr utilizzabile, se il titolo interno MediaInfo contiene un nome release con titolo e stagione/episodio
coerenti con il filename, viene usato per recuperare sorgente e releaser. I titoli
semplici, senza risoluzione o codec, e quelli di altri film o episodi vengono ignorati.
In caso di conflitto, il wizard e la CLI segnalano i tag sostituiti: controlla il nome
proposto prima di confermare. Il titolo interno è un indizio di provenienza, non una
certificazione della sorgente.

`NFRip` viene normalizzato in `NF WEBRip`. WEBRip resta distinto da WEB-DL; per
un WEBRip HEVC il nome usa `x265`. Il releaser presente nel titolo interno viene
preservato anche se manca nel filename. Senza un titolo interno utilizzabile,
rimangono i tag ricavati dal filename (con fallback del releaser alla cartella per le serie).

Il codec audio proviene dalla traccia predefinita, oppure dalla prima se non è
indicata una predefinita. Il numero di canali è il massimo tra tutte le tracce:
con ITA stereo ed ENG 5.1, il nome riporta `ITA ENG AAC 5.1` se il codec predefinito è AAC.

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
