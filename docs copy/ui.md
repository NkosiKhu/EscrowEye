# EscrowEye UI Layout

The owner and supplier application surfaces are mirrored for job and bid workspaces.
For both job and bid detail pages, the structured context occupies the top third of
the screen and the chat interface occupies the remaining two thirds.

Owner-only create pages do not include chat.

## Owner Jobs

```text
OWNER: JOBS LIST / DASHBOARD
┌─────────────────────────────────────────────────────────────┐
│ EscrowEye                                                   │
├──────────────┬──────────────────────────────────────────────┤
│ Owner Nav    │ Jobs                                         │
│              │ ┌──────────────────────────────────────────┐ │
│ Homes        │ │ Job row                                  │ │
│ Jobs         │ ├──────────────────────────────────────────┤ │
│              │ │ Job row                                  │ │
│              │ ├──────────────────────────────────────────┤ │
│              │ │ Job row                                  │ │
│              │ └──────────────────────────────────────────┘ │
└──────────────┴──────────────────────────────────────────────┘
```

## Owner Create Home

```text
OWNER: CREATE HOME PAGE
┌─────────────────────────────────────────────────────────────┐
│ EscrowEye                                                   │
├──────────────┬──────────────────────────────────────────────┤
│ Owner Nav    │ Add Home                                     │
│              │                                              │
│ Homes        │ ┌──────────────────────────────────────────┐ │
│ Jobs         │ │ Home name                                │ │
│              │ │ Address                                  │ │
│              │ │ Rooms                                    │ │
│              │ │                                          │ │
│              │ │ [Add Room]                 [Save Home]   │ │
│              │ └──────────────────────────────────────────┘ │
│              │                                              │
│              │ No chat on this page                         │
└──────────────┴──────────────────────────────────────────────┘
```

## Owner Create Job

```text
OWNER: CREATE JOB PAGE
┌─────────────────────────────────────────────────────────────┐
│ EscrowEye                                                   │
├──────────────┬──────────────────────────────────────────────┤
│ Owner Nav    │ Create Job                                   │
│              │                                              │
│ Homes        │ ┌──────────────────────────────────────────┐ │
│ Jobs         │ │ Select home                              │ │
│              │ │ Title                                    │ │
│              │ │ Description / scope                      │ │
│              │ │ Price / availability / access notes      │ │
│              │ │                              [Post Job]  │ │
│              │ └──────────────────────────────────────────┘ │
│              │                                              │
│              │ No chat on this page                         │
└──────────────┴──────────────────────────────────────────────┘
```

## Owner Job View

```text
OWNER: JOB VIEW
┌─────────────────────────────────────────────────────────────┐
│ EscrowEye                                                   │
├──────────────┬──────────────────────────────────────────────┤
│ Owner Nav    │ Job Detail                      top 1/3      │
│              │ ┌──────────────────────────────────────────┐ │
│ Homes        │ │ Title / status / rooms / photos / bids   │ │
│ Jobs         │ │ [Award Bid] [Fund Escrow] [Confirm]      │ │
│              │ └──────────────────────────────────────────┘ │
│              ├──────────────────────────────────────────────┤
│              │ Chat Interface                 bottom 2/3   │
│              │ ┌──────────────────────────────────────────┐ │
│              │ │ Owner / supplier / agent messages        │ │
│              │ │ Photo review messages                    │ │
│              │ │                                          │ │
│              │ │ Type message...              [Send]      │ │
│              │ └──────────────────────────────────────────┘ │
└──────────────┴──────────────────────────────────────────────┘
```

## Owner Bid View

```text
OWNER: BID VIEW
┌─────────────────────────────────────────────────────────────┐
│ EscrowEye                                                   │
├──────────────┬──────────────────────────────────────────────┤
│ Owner Nav    │ Bids                           top 1/3      │
│              │ ┌──────────────────────────────────────────┐ │
│ Homes        │ │ Bid card      Bid card      Bid card     │ │
│ Jobs         │ │ Amount        Supplier      Message      │ │
│              │ │                    [Choose Best Bid]     │ │
│              │ └──────────────────────────────────────────┘ │
│              ├──────────────────────────────────────────────┤
│              │ Chat Interface                 bottom 2/3   │
│              │ ┌──────────────────────────────────────────┐ │
│              │ │ Clarifications about bid / job           │ │
│              │ │ Agent suggestions                        │ │
│              │ │                                          │ │
│              │ │ Type message...              [Send]      │ │
│              │ └──────────────────────────────────────────┘ │
└──────────────┴──────────────────────────────────────────────┘
```

## Supplier Jobs

```text
SUPPLIER: JOBS LIST / DASHBOARD
┌─────────────────────────────────────────────────────────────┐
│ EscrowEye                                                   │
├──────────────┬──────────────────────────────────────────────┤
│ Supplier Nav │ Jobs                                         │
│              │ ┌──────────────────────────────────────────┐ │
│ Jobs         │ │ Available job row                        │ │
│ Bids         │ ├──────────────────────────────────────────┤ │
│              │ │ Available job row                        │ │
│              │ ├──────────────────────────────────────────┤ │
│              │ │ Assigned job row                         │ │
│              │ └──────────────────────────────────────────┘ │
└──────────────┴──────────────────────────────────────────────┘
```

## Supplier Job View

```text
SUPPLIER: JOB VIEW
┌─────────────────────────────────────────────────────────────┐
│ EscrowEye                                                   │
├──────────────┬──────────────────────────────────────────────┤
│ Supplier Nav │ Job Detail                      top 1/3      │
│              │ ┌──────────────────────────────────────────┐ │
│ Jobs         │ │ Title / status / rooms / access notes    │ │
│ Bids         │ │ [Upload Photos] [Mark Ready] [Dispute]   │ │
│              │ └──────────────────────────────────────────┘ │
│              ├──────────────────────────────────────────────┤
│              │ Chat Interface                 bottom 2/3   │
│              │ ┌──────────────────────────────────────────┐ │
│              │ │ Supplier / owner / agent messages        │ │
│              │ │ Uploaded photos + review feedback        │ │
│              │ │                                          │ │
│              │ │ Type message...        [Photo] [Send]    │ │
│              │ └──────────────────────────────────────────┘ │
└──────────────┴──────────────────────────────────────────────┘
```

## Supplier Bid View

```text
SUPPLIER: BID VIEW
┌─────────────────────────────────────────────────────────────┐
│ EscrowEye                                                   │
├──────────────┬──────────────────────────────────────────────┤
│ Supplier Nav │ Bid Detail                      top 1/3      │
│              │ ┌──────────────────────────────────────────┐ │
│ Jobs         │ │ Job summary / current bid / status       │ │
│ Bids         │ │ Bid amount / message / [Update Bid]      │ │
│              │ └──────────────────────────────────────────┘ │
│              ├──────────────────────────────────────────────┤
│              │ Chat Interface                 bottom 2/3   │
│              │ ┌──────────────────────────────────────────┐ │
│              │ │ Bid clarification messages               │ │
│              │ │ Owner / supplier / agent conversation    │ │
│              │ │                                          │ │
│              │ │ Type message...              [Send]      │ │
│              │ └──────────────────────────────────────────┘ │
└──────────────┴──────────────────────────────────────────────┘
```
