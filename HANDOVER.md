# Overdracht Document - v1.7.0-BROKEN

**Datum**: 13 januari 2026  
**Status**: AFGEBROKEN - Niet productierijp  
**Aanbeveling**: Terug naar v1.6.6 of grondig reviewen

---

## Samenvatting

De sessie begon met het fixen van bugs uit v1.6.6 maar is ontspoord. Er zijn wijzigingen gemaakt zonder volledig begrip van de bestaande code. De gebruiker is terecht gefrustreerd.

---

## Originele Bug Lijst (van gebruiker)

1. **Preview kapot** - Niet getest/opgelost
2. **CastCards volgorde wisselt** - Poging tot fix met `updateCastCardRefs()`
3. **AudioDNA vak rolt uit** - CSS meerdere keren aangepast, werkt nog niet
4. **Rendert voor ELKE scene een wardrobe** - Niet onderzocht
5. **Maakt geen B scenes** - Niet onderzocht
6. **Castref soms niet meegestuurd** - Poging tot fix met ref_a/ref_b selectie
7. **Cost klopt niet** - `note` parameter toegevoegd

---

## Wat er is gewijzigd

### main.py

1. **Style lock prompt instructie** (regel ~783):
```python
style_instruction = "match the artistic style and color palette of the second reference image, do not include or blend the person from that reference, " if style_lock_url else ""
```
Bedoeling: AI vertellen dat style_lock voor stijl is, niet om persoon toe te voegen.

2. **ref_a/ref_b selectie** (regel ~2005):
```python
camera_lang = (shot.get("camera_language") or "").lower()
use_closeup = any(kw in camera_lang for kw in ["close-up", "closeup", "close up", "portrait", "head shot", "headshot", "face", "eyes"])
ref_key = "ref_b" if use_closeup else "ref_a"
```
Bedoeling: Close-up shots gebruiken ref_b (portret), anderen ref_a (full body).

3. **Cost tracking note** (services/config.py):
```python
def track_cost(model, count=1, state=None, note=None):
    # ... 
    call_entry["note"] = note
```

4. **FFmpeg debug logging** (regel ~2404):
Debug prints toegevoegd voor concat_file, audio_path, output_path.

### static/app.js

1. **updateCastCardRefs()** (regel ~2565):
Nieuwe functie om cast card refs te updaten zonder hele lijst te re-renderen.
Bedoeling: Voorkomen dat cast cards van volgorde wisselen.

### static/style.css

1. **Lyrics CSS** - Meerdere pogingen, geen werkende oplossing.
Huidige staat zou gelijk moeten zijn aan v1.6.5 maar werkt niet.

---

## Kernprobleem: Style Lock

Het fundamentele probleem dat niet is opgelost:

- `style_lock_image` is de ref_a van de EERSTE cast member (een persoon)
- Deze wordt als `ref_images[1]` naar FAL gestuurd bij elke cast ref generatie
- FAL's img2img interpreteert dit als "deze persoon moet in het beeld"
- De prompt zegt nergens expliciet "negeer de persoon, kopieer alleen de stijl"

**Toegevoegde fix** (niet getest):
Een prompt instructie toegevoegd, maar het is onduidelijk of FAL dit respecteert.

**Betere oplossing** zou zijn:
- Style lock op een DECOR image baseren, niet op een persoon
- Of een apart style_lock veld dat expliciet GEEN persoon bevat

---

## Audio/Cast Hoogte Sync

### Originele logica (v1.5.9):
- `cast.length <= 3`: Lyrics heeft vaste 200px hoogte
- `cast.length > 3`: `.cast-expanded` class → lyrics groeit mee

### Probleem:
De gebruiker wil dat Audio DNA en Cast Matrix ALTIJD gelijke hoogte hebben, ongeacht aantal cast. De huidige logica ondersteunt dit niet.

### CSS staat nu:
Teruggezet naar v1.6.5 versie maar werkt nog niet correct volgens gebruiker.

---

## Files die gewijzigd zijn (check git diff)

```
main.py
static/app.js  
static/style.css
services/config.py
services/render_service.py
CHANGELOG.md
```

---

## Aanbevelingen voor reviewer

1. **Start met git diff tegen v1.6.6** om alle wijzigingen te zien
2. **Test style lock** met meerdere cast members - komt eerste persoon in beeld?
3. **Test audio/cast hoogte** - groeit lyrics mee met cast?
4. **Test preview/export** - werkt FFmpeg?
5. **Overweeg rollback** naar v1.6.6 en begin opnieuw met één bug tegelijk

---

## Git commando's

```bash
# Bekijk alle wijzigingen sinds v1.6.6
git diff c8afc3d..HEAD

# Rollback naar v1.6.6 (harde reset)
git reset --hard c8afc3d

# Of maak nieuwe branch vanaf v1.6.6
git checkout c8afc3d -b v1.6.6-clean
```

---

## Excuses

De sessie is slecht verlopen door:
- Te snel wijzigingen maken zonder de code volledig te begrijpen
- CSS aanpassingen zonder de grid/flex hiërarchie te doorgronden
- Niet terugkijken naar werkende versies toen problemen zich opstapelden
- Proberen te maskeren in plaats van fouten toe te geven

De gebruiker verdient een schone lei met een agent die de code wel begrijpt.
