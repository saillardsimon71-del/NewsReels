# NewsReel V2 — JT satirique full-H3

NewsReel transforme des actualités en un JT vertical satirique dans `output/<run_id>/newsreel_final.mp4`.

La V2 restaure la couche créative historique du NewsReel : **25 directions artistiques**, **16 palettes**, costumes rétrofuturistes, décors hallucinatoires, gags physiques, personnages secondaires, Stanislavski, caméra, lumière et texture. Agnes écrit le scénario et génère les keyframes. FastH3 anime **le présentateur et les reporters** avec audio natif. FFmpeg reste le monteur local.

Pour trois sujets, un run produit **6 clips H3 dans un seul appel Modal** :

```text
intro graphique local
host 1 H3 → reporter 1 H3
host 2 H3 → reporter 2 H3
host 3 H3 → reporter 3 H3
outro graphique local
→ FFmpeg → newsreel_final.mp4
```

## Couche créative

La logique historique est portée dans `newsreel/creative.py` :

- `DIRECTORS` : 25 grammaires visuelles avec style, caméra, lumière et texture ;
- `PALETTES` : 16 familles chromatiques saturées ;
- prompt scénario historique : host factuel, reporter comique, sketch physique autonome, 3–5 personnages secondaires, univers rétrofuturiste ;
- prompts image host / reporter ;
- prompts vidéo host / reporter adaptés à la syntaxe audio native H3 `<d>[French] ...</d>` ;
- post-traitement créatif historique : fallbacks, longueurs de dialogue, costumes rétrofuturistes et architecture hallucinatoire.

Le contrôle `intensity` est conservé dans l'interface pour compatibilité, mais comme dans l'ancien NewsReel il n'altère pas encore les prompts.

## FastH3 / Modal

Le graphe ComfyUI API est construit directement en Python dans `newsreel/h3_workflow.py` et exécuté par `modal_h3.py`. Aucun workflow JSON externe n'est nécessaire.

Configuration validée :

- FastH3 8-Step V2 / MiniMax H3 ;
- 768×1344, 243 frames, 24 fps, 10,125 s ;
- 8 steps, sampler `res_multistep`, scheduler `simple` ;
- audio natif H3 ;
- sigma shift vidéo 10 / audio 3 ;
- Comfy Kitchen attention + VSA ;
- L40S 48 Go, 8 CPU, 98304 MiB RAM ;
- `max_containers=1`, `single_use_containers=True` ;
- volume Modal `fasth3-models`.

Les quatre poids attendus sont :

```text
diffusion_models/fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors
text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
vae/minimax_h3_video_vae_int8_convrot.safetensors
vae/minimax_h3_audio_vae_fp32.safetensors
```

Un seul conteneur ComfyUI traite séquentiellement tous les clips du JT puis s'arrête.

## Architecture

```text
bridge.py                       API FastAPI locale + UI + progression
modal_h3.py                     worker Modal full-H3
newsreel/creative.py            ADN créatif historique NewsReel
newsreel/agnes.py               scénario + images Agnes
newsreel/models.py              scénario / timeline sérialisables
newsreel/h3_workflow.py         graphe FastH3 construit en code
newsreel/h3_worker_contract.py  prompts H3 + batch host/reporter
newsreel/timeline.py            ordre des scènes
newsreel/assembler.py           overlays + montage H.264/AAC local
newsreel/news.py                Google News RSS
newsreel/run_store.py           isolation output/<run_id>
web/index.html                  studio V2 sans framework
newsreel/demo.py                démo full-H3 synthétique hors-ligne
```

## Installation Windows

Depuis le clone de test :

```powershell
cd "$HOME\Downloads\NewsReels-test"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-modal.txt
```

FFmpeg et ffprobe doivent être disponibles :

```powershell
ffmpeg -version
ffprobe -version
```

## Déployer le worker et lancer le studio

Après chaque modification du worker ou du package `newsreel`, redéployer Modal :

```powershell
modal deploy modal_h3.py
```

Puis lancer le bridge :

```powershell
python bridge.py
```

Ouvrir **http://127.0.0.1:8000**. L'interface expose le nombre de sujets, la catégorie, le réalisateur, la palette et l'intensité historique, ainsi que la configuration Agnes.

La clé Agnes peut être saisie dans l'interface ou définie par `AGNES_API_KEY`. Elle n'est pas écrite dans le manifeste.

## Démo et tests hors-ligne

```powershell
python -m pip install -r requirements-dev.txt
python -m newsreel.demo
python -m pytest -q
ruff check .
python -m compileall -q newsreel bridge.py modal_h3.py
```

La démo ne contacte ni Agnes ni Modal et n'utilise aucun GPU. Elle fabrique localement six clips vidéo synthétiques pour vérifier la forme full-H3, la timeline, les overlays, l'audio et le MP4 final.

## API locale

- `GET /health` — FFmpeg / Modal / état du bridge ;
- `GET /config` — modèles Agnes + catalogue créatif ;
- `POST /runs` — run complet Agnes → full-H3 → FFmpeg ;
- `POST /demo` — fixture hors-ligne ;
- `POST /render-h3-batch` — relance le batch H3 d'un run existant ;
- `POST /assemble` — remonte le `timeline.json` ;
- `GET /run/<run_id>` — progression, manifeste et timeline ;
- `GET /output/<run_id>/<path>` — fichiers du run.

Chaque run est isolé. `scenario.json` persiste aussi la configuration créative utilisée afin qu'un rendu soit reproductible.
