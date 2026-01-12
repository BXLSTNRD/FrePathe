## v1.6.0 -> v1.6.1

Titelmodule:
    -Versie updaten naar 1.6.1
    -logo updaten (meegeleverd)

Pipelinemodule:
    -Cost oplossen!!! Check de prijzen; tel de renders (Check en tel ook de LLM kost...) prijzen bijgevoegd

Projectmodule:
    -Niks aanpassen at the moment

AudioDNAmodule:
    -> Werkt Audio expert al -> Hij called audio-understanding moet whisper zijn dan voor lyrics

CastMatrixmodule:
    - Geen icon bij style lock alleen when locked (monotone icons overal; 't is geen kleurboek :p )
    - In CastCards: Idle staat in het invulveld "Keywords..." maak ervan "Extra prompt..."
    - Uiterst rechts van dat promptveld een rerenderbutton zoals bij de SceneCards en ShotCards
    - Geef die prompt dubbel impact over de base

## v1.6.1 -> v1.6.2

Storyboardmodule -> v1.6.2
    - De LLM had al extra creatieve ruimte gekregen met Wardrobe injectie; we verruimen dat. Hij mag per scene 2 verschillende decors genereren ENKEL indien dit bijdraagt tot het later samenstellen van shots. (bvb flashbacks ea)
    - In SceneCards: Icoon Wardrobe lelijk -> Gele hoed simpel
    - In SceneCards: reprompter en button verhuist naar zijn popup
    - ScenePopup: Image wordt 1:1 weergegeven; ook al is het anders + integratie bonusdecor en reprompter + generatie 1 img wardroberef=CastIDrefA+Decor
    - Lock functie Decor Scene
    - Lock functie Wardrobe Scene

Kleine algemene UI:
Eens AUDIO EN CAST Fully locked zijn clolapsen die tot enkel hun titel en locklabel
Eens alle scenes decor en wardrobe locked hebben same

## v1.6.2 -> v1.6.3

-Titels audio en cast terugzetten waar ze stonden; links uitlijnen ipv centraal
-Audio DNA niet automatisch locken. -> Button krijgt 3 stages = Import audio - Lock Audio - Audio Locked
- Castcards; als rerender ALTIJD editprompt meenemen ; status "rerender img" te zien in Pipelinestatus; moet in Castmatrix status zijn... ; rerenders refreshen niet of toch niet allemaal ; 
- collapsables moet open en dicht kunnen; is nu niet zo
- storyboard maakt decorb maar ik zie ze ni

## v1.6.3 AUDIT

## v1.6.3 -> v1.6.4

-SceneRenders: EXCLUSIEF VERBOD OP MENSEN (Was al); EXCLUSIEF VERBOD OP TEKST UIT DE LYRIC/TITEL/STYLE (bvb thunderbirds inject overal hun merknaam)

-SceneCards:
    - dezelfde loadingstyle geven als de shotcards; ik bedoel de kleuromlijning en inhoud thumb tijdens verwerken en finish
    - symbool extra decor verschijnt niet
    - symbolen decor en wardrobe niet op de rand van de thumb weergeven; zet ze onderaan in de tweede kolom rechts uitgelijnd. en monotoon!!! KLEUR FréGeel : is zelfde als buttongeel 

-SceneCards Pop-up:
    - Kolom A renders
        - De image van decor1 is er; Die van decor2 ook maar niet dezelfde size
        - Bij renderen wardrobe geen render zichtbaar (Fal maakt hem wel)
        - maak die 3 renders even groot en klikbaar voor fullsize
        -Als andere cast ook wardrobe nodig heeft dan uitbreiden per cast.
    - Kolom B: omschrijving + edits + lock
        - Elke Image uit kolom A krijgt een: Omschrijving met daaronder een prompveld voor edit ; mogelijkheid een img aan die prompt toe te voegen (bovenop de original die we editen) en een pijltje om die prompt door te voeren (analoog aan castsyseem) -> render ok of rerender ok -> klein lockbuttontje naar analogie met de 'make refs button' uit cast

-Shotcards:
    - Waar zijn mijn mooie editveldjes naartoe met "promptveld" "+" en "->" 
    - Sommige promts krijgen GEEN personage mee terwijl hun naam DUIDELIJK in prompt zit
    - Juiste prompts meekrijgen; indien decor2 - gebruik die dan; indien Wardrobe nodig gebruik die dan.

UI TIMELINE:
collabsable als alles gelocked
