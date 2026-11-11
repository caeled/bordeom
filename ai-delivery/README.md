# AI-Delivery staging — Muse

Bridge between Muse (chat agent) and Steven's AI-Delivery folders on PowellServer, carried by Muse running on Steven's machine.

- inbox/ — files Muse created FOR Steven, named YYYY-MM-DD_short-description.ext. The local interface copies them into C:\Users\ntadmin\AI-Delivery\Inbox\MUSE\ keeping the exact filename.
- outbox/ — files Steven wants Muse to review, pushed here by the local interface under their existing names.
- Do not rename files in transit.
