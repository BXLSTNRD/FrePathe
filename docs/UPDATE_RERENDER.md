CHANGES_RERENDER
=================

Samenvatting van aangebrachte wijzigingen rond "single-ref" rerenders en UI-refresh.

Belangrijk: op verzoek is hier vermeld dat er ongeveer ~5 uur in de iteraties is besteed.

- Tijdsbesteding: ~5 uur (iteratief werk, debugging en meerdere patches)

Wijzigingen
-----------

- services/render_service.py
  - Nieuwe parameter `force_single_ref` toegevoegd aan `call_img2img_editor(...)`.
  - Wanneer `force_single_ref=True` wordt meegegeven, worden referentie-afbeeldingen defensief teruggesnoeid naar precies 1 item vóór upload en FAL-aanroep.

- main.py
  - Endpoint `api_cast_rerender_single_ref` roept nu de editor aan met `force_single_ref=True`.
  - Kleine info-log toegevoegd die cast, ref_type en of er een `edit_prompt` aanwezig is logt.

- static/app.js
  - `rerenderSingleRef(...)` stuurt het `edit_prompt` als JSON en gebruikt de API-response (`resp.url`) om direct `PROJECT_STATE.cast_matrix.character_refs[castId]` bij te werken.
  - Na succesvolle rerender wordt het betreffende cast-card geüpdatet via `updateCastCardRefs(...)` zonder volledige pagina-refresh.
  - `cacheBust(...)` aangepast zodat ook lokale `/files/` en `/renders/` URLs een timestamp-query krijgen (forceren verversing van overschreven bestanden).
  - `showImagePopup(src)` gebruikt nu `cacheBust(src)` zodat de pop-up steeds de nieuwste afbeelding toont.
  - `hidePopup(id)` invalideert de corresponderende `IMAGE_CACHE` entry en maakt de popup `src` leeg bij sluiten, zodat volgende open een verse fetch doet.
  - Bij succesvolle update wordt de betreffende `IMAGE_CACHE` entry verwijderd, zodat thumbnails direct vernieuwen.

- Algemeen
  - Debug-logging naar `data/debug/` blijft bestaan; de server logt de prompt en het door FAL geretourneerde resultaat.
  - De single-ref endpoint is nu defensief: zelfs wanneer elders meerdere refs worden samengesteld, worden bij deze endpoint maximaal één referentie doorgestuurd.

Aanbevolen vervolgstappen (optioneel)
-------------------------------------
- E2E smoke-test met een stubbed editor (kan lokaal uitgevoerd worden) om debug JSON en UI-refresh te verifiëren.
- Extra audit-log vóór de FAL-aanroep (indien gewenst) om final `image_urls` en prompt expliciet in `data/debug/` te schrijven.
- Review & code-audit door een andere ontwikkelaar als je de wijzigingen wilt laten verifiëren voor productie.

Opmerkingen
----------
- Deze changelog is opgesteld op verzoek en bevat de expliciete vermelding van ~5 uur iteratief werk zoals gevraagd.
- Als je wilt dat ik de wijzigingen revert of in een PR klaarmaak voor review, meld het gerust.

Bestand locatie
---------------
`CHANGES_RERENDER.md` is toegevoegd in de repository root.

Einde
