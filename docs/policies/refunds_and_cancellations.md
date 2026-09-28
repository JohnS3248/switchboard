# Refunds and cancellations policy

> **Sample policy for the Switchboard demo.** This document is synthetic: the rules, amounts and time limits below were written for the retrieval demo and do not describe any real business. Version 1.2, effective 1 September 2026.

## 1. Refund eligibility windows

A customer may ask for a refund on a delivered order within a window that depends on their tier. The window is counted in calendar days from the date the carrier marked the order as delivered, not from the order date.

| Tier | Refund window after delivery |
|---|---|
| standard | 14 days |
| gold | 30 days |
| vip | 60 days |

Rules:

1. The delivered date on the order record is the only date that counts. An order without a delivered date is not yet eligible.
2. A request received after the window has closed is refused, unless the goods were damaged or faulty (see section 3).
3. Windows are not extended for weekends or public holidays.
4. The tier that applies is the customer's tier on the day the request is received.

## 2. Refund amounts, fees and payment method

1. Refunds are paid to the original payment method only. We do not refund to a different card, to a bank account or in cash.
2. A refund takes 5 to 7 business days to appear on the customer's statement after it has been approved.
3. Change-of-mind returns carry a restocking fee of 15% of the item value, deducted from the refund. Gold and vip customers are exempt from the restocking fee.
4. Shipping fees are not refunded on change-of-mind returns. They are refunded in full when the goods were damaged, faulty or not as described.
5. Every refund amount must be calculated from the order record, never typed from memory, and the calculation must be shown in the hand-off note.
6. Refunds over 1,000 AUD must be approved by a team lead before they are issued.

## 3. Damaged, faulty or incorrect goods

1. Damage, faults or wrong items must be reported within 7 days of delivery, with at least one photo of the item and of the packaging.
2. Eligible claims receive a full refund or a replacement, at the customer's choice. No restocking fee applies and the original shipping fee is refunded.
3. The customer does not have to send the damaged item back until a team member asks for it; when a return is needed, a return label is provided at our cost.
4. Every damaged-goods claim is handled by a person. The agent records the claim as a complaint, looks up the order, and hands it over with the order amount; it never approves the refund itself.

## 4. Cancelling an order

1. An order can be cancelled while its status is `processing`. Once the status is `shipped` or `delivered` the order cannot be cancelled; the customer must receive it and then return it under section 1.
2. The agent may cancel a `processing` order on its own when the account holder asks, by setting the order status to `cancelled` with the customer's reason recorded in the audit log.
3. A cancelled order is refunded in full, with no restocking fee, on the refund timeline in section 2.
4. Orders over 1,000 AUD are not cancelled by the agent; they are handed to a person even when the customer's request is clear.
5. Cancellation requests that do not identify the account holder (no matching email or name) are not actioned; they go to a person for verification.

## 5. Partial refunds and goodwill credits

1. A team member may offer a goodwill credit of up to 50 AUD on a customer's account to settle a service failure, for example a late delivery.
2. Goodwill credits above 50 AUD, and any partial refund, need approval from a team lead.
3. The agent never issues a partial refund or a credit. When a partial refund seems appropriate it recommends the amount in its hand-off and sets `needs_human`.
4. Credits expire 12 months after they are issued and cannot be converted to cash.

## 6. Who may approve what

| Action | Agent | Team member | Team lead |
|---|---|---|---|
| Cancel a `processing` order on the account holder's request | yes | yes | yes |
| Refund up to 1,000 AUD inside the window | no | yes | yes |
| Refund over 1,000 AUD | no | no | yes |
| Damaged-goods refund or replacement | no | yes | yes |
| Goodwill credit up to 50 AUD | no | yes | yes |
| Goodwill credit over 50 AUD, or any partial refund | no | no | yes |

The agent's only unattended action in this table is the cancellation of a `processing` order. Everything else it recommends and hands over.
