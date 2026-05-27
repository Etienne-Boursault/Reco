#!/usr/bin/env bash
# Sauvegarde les transcripts ACAST des 21 épisodes en .acast.txt
# avant qu'ils ne soient écrasés par la re-transcription YT.
set -e
cd ~/transcripts/un-bon-moment

GUIDS="61cb19444f2d030012ddd82a 6302667b4913bd00126c374c 6550c05703445c0011dd8343 \
6550c2836b767e0012a65d8d 9536da14-4023-4a5b-b6e3-d6a73a405eb1 \
6c166c4a-6617-4176-a9ad-5bcf874c9b6b 712ea7fc-593d-472e-99ae-9ca35fcd2a05 \
7870d7fa-cb20-4051-8458-27dbf903dbe8 652406c019376d001282c4d8 \
65240e1c5d8481001225962c 6584658132930b0016c5272b 6599de12076e6c001696556a \
65c7a2673210d00017783f8b bf76185c-2ca0-4324-9adf-a7977d745a2d \
8fea089a-4ebc-4aff-a90a-9ed6a94a30be 6322de1f35ce9e001229f98a \
633b305f3ca1cc001201a861 65240aefc8996500127ede97 65240f8a7a4ced00123481d1 \
6a10a31516a6aa135ed729e1 633b2f213ca1cc001201a69f cbfadce5-1677-43ec-8665-8b47daeda6b7"

n=0
for g in $GUIDS; do
    if [ -f "$g.txt" ]; then
        cp -n "$g.txt" "$g.acast.txt"
        n=$((n+1))
        echo "  backup $g ($(du -h $g.acast.txt | cut -f1))"
    else
        echo "  (absent côté portable : $g)"
    fi
done
echo "Total : $n sauvegardés."
