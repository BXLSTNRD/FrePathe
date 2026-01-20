1.8.1 -> DONE - Image2Video implementeren (Basis OK)

1.8.2 -> Promptrerenders JUIST ZETTEN - (OK)
      -> Master negprompt to rule over all (DONE)
      -> thumb/cardupdate bij rerender... (OK)
      -> Concurrency voor video verhogen (DONE)

1.8.3 -> CastMatrix Rerender Workflow - (DONE)
      -> Style Lock Complete Removal - (DONE)
      -> Async RefA/RefB Generation (Optimization #5) - (DONE)
      -> ORG-IMG Upload Bug Fix - (DONE)
      -> Thumbnail Cache Invalidation - (DONE)

1.8.4 -> BUGFIX
      -> UI Overhoal
      -> Styles+Prompts masterfinetunen
      -> GPT1.5-Edit toevoegen

1.8.5 -> Save/Load -> Weg uit data; userfriendly
            -> Seriously; updaten van een oud project naar een nieuw maakt wel nieuwe map met JSON aan.
             Maar de oude MAG ni weg; daar zitten de helft vd renders... DUH  
             En Alles wat verspreid zit... ALLES IN PJCTMAP OOK Debugfiles
             Geen dubbele JSON onder prjocttitle en interne ID (Interne ID weg!!!)
      -> Optimalisatie CastMatrix (Queue Systeem)
            -> Zie docs/CAST_MATRIX_OPTIMIZATIONS.md
            -> Smart queueing: batch similar ref generations
            -> Intelligent RENDER_SEMAPHORE utilization
            -> Priority system (user-initiated > auto-batch)       
      -> cost

REFACTOR
1.8.5 -> Dead Code Purge
1.8.6 -> Standards enforcement
1.8.7 -> Persistence + concurrency hard maken
1.8.8 -> Cleanup Backlog
1.8.9 -> Securety verhogen

DEBUGGING
v1.9 -> v1.9.9

Beta v2 release (01/02/2026)
