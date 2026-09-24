# Partner audiobook holds — live test, 2026-09-23

The 2026 Booker list was searched across the two home and 22 partner catalogs.
The account initially had only two home cards. Libby's official website offered
visitor access when an audiobook's **Place Hold** action was opened at a partner
collection. Selecting **Continue** linked a visitor card to the same identity.
The CLI's next native account sync then showed that card, its separate hold
limit, and its catalog key. No library card numbers, PINs, or tokens are recorded
here.

Eight audiobook holds were placed with the CLI. Each request used an exact
catalog title ID, checked the card's current hold capacity and title
availability, and verified the resulting hold in a fresh account sync.

| Audiobook | Hold library | Access through |
| --- | --- | --- |
| Switzy | Boston Public Library | Minuteman Library Network |
| Black Bag | Boston Public Library | Minuteman Library Network |
| All Them Dogs | Boston Public Library | Minuteman Library Network |
| The End of Everything | Download Destination | Up North Digital Collection |
| May We Feed the King | Download Destination | Up North Digital Collection |
| The Things We Never Say | St. Clair County Library System | Up North Digital Collection |
| John of John | St. Clair County Library System | Up North Digital Collection |
| The Disappearers | Merrimack Valley Library Consortium | Minuteman Library Network |

A final account sync showed exactly one hold for each of these eight works and
no hold for *The Renovation*. Four other longlist titles had no confident
audiobook catalog match, so no hold was attempted for them.

The live test establishes that this account can place holds through these four
partner visitor cards. It does not establish that every partner permits holds:
[Libby's partnership help](https://help.libbyapp.com/en-us/6350.htm) says
partner rules may restrict holds or waiting-list priority. Public catalog wait
estimates can differ from the personalized estimate shown when placing a hold.

The CLI now keeps visitor cards classified as partner access in `libraries
connected` and marks them as linked. `circulation hold --library KEY` chooses a
linked card by catalog key; it avoids card-number changes when visitor cards
are added. Partner visitor-card activation still takes place in Libby's own
interface. The CLI does not create those cards through its private service.
