# Here's what I'd do next

*(Written 2026-10-16. First person: this is my read of where the Ledger stands, not a finding about any well site.)*

Where things are: the location bug is fixed at the source, with 21,340 of 22,057 sites pinned to a surveyed surface hole and 717 refused as "location unverified". The tier rule is now CI-gated. On 98 no-well points it flagged 3 (3.1%, 95% upper bound 8.6%), under the 5% line I committed before running. The old rule flagged 13 of the same 98 and failed. That pass is a regression check on points and chips I had already seen, so it shows the rule isn't reading regional weather as recovery. It does not show that the screen can see reclamation. Ten-metre pixels still can't resolve many well pads.

1. **Merge #33, then #41.** The publication hold stays on while everything below is tested.
2. **Run a fresh, pre-registered control.** That means new no-well points I haven't seen, the pass line committed first, and the result published whether it passes or fails.
3. **Test pad-vs-ring at 10 m on roughly 0.25 ha pads.** How often can a pad that size be told apart from the land around it? The answer sets what the screen can say at all, and where it has to answer "not assessable".
4. **Interview three buyers about a calibrated screening benchmark:** a closure-team lead, an ESG or insurance analyst, and a journalist or researcher. I'd ask whether a published false-alarm rate and "not assessable" rate would change a decision they make, not whether they like the idea.

If the control passes and the interviews are positive, build it; if either fails, stop.
