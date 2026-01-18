Patches toegepast.

Kort overzicht van wat ik aangepast heb (exact, binnen scope Cast-rerenders):

Backend: api_cast_rerender_single_ref in main.py

Nieuwe signature accepteert payload: Dict[str, Any] = None.
Vereist nu edit_prompt in payload; als ontbreekt → HTTP 400.  ----------> Neen; leeg veld = nieuwe render met dezelde prompt als firstrender + origenele refabeelding; Wel ingevuld stuurt firstrender waarvan je een edit wil... ietswijzigen aan refA : refAfirstrender meesturen.   <---------- 

Stuurt alleen dat korte edit_prompt als prompt naar call_img2img_editor. -----> Serverside krijgt die een kleine aanvulling "Make EXACT THE SAME IMAGE Except for..."  <---------------

Gebruikt precies één referentie: de bestaande canonical ref (refs[0]). -------------> Dus A wijzigen is A meesturen; B wijzigen is B meesturen...  <------------------
Rest van het gedrag (opslaan van lokaal pad, kostenlog, thread-safe save) ongewijzigd.
Frontend: rerenderSingleRef in app.js

Vraagt gebruiker met window.prompt() om een korte edit-instructie.    -------> Geen window.prompt nodig; zit al in UI -> UI Hoeft niet te wijzigen   <----------------
Als gebruiker annuleert → operatie afgebroken.
Stuurt POST met JSON body { edit_prompt: "..." } naar de aangepaste API.
Vervangt het vorige gedrag dat geen payload stuurde.


ZIE AFBEELDING; Het promptvak is er; drie herrenderbuttons; Allebei samen met die prompt of elk apart met andere prompt corrigeren...


Te bekijken LAADTIJDEN vd renders en hun toewijzing aan de juiste CastID (loopt mis als je drie personages invuld en de imgs komen niet in juiste volgorde terug...)