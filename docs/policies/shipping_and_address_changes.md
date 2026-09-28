# Shipping and address changes policy

> **Sample policy for the Switchboard demo.** This document is synthetic: the carriers, fees and delivery estimates below were written for the retrieval demo and do not describe any real business. Version 1.1, effective 1 September 2026.

## 1. Shipping methods, fees and delivery times

| Method | Metro estimate | Regional estimate | Fee |
|---|---|---|---|
| Standard | 3 to 5 business days | 5 to 8 business days | 9.95 AUD, free on orders of 150 AUD or more |
| Express | 1 to 2 business days | 2 to 4 business days | 14.95 AUD flat |

1. Estimates count business days from the day the order is marked `shipped`, not from the order date.
2. Orders placed before 2 pm Melbourne time on a business day are dispatched the same day; later orders are dispatched the next business day.
3. Express is not available for parcels over 20 kg or for PO boxes and parcel lockers (see section 6).
4. The shipping fee actually charged is on the order record; the agent reads it from there rather than assuming it.

## 2. Changing the delivery address

1. A delivery address can be changed while the order status is `processing`. Once the order is `shipped`, the address cannot be changed by us; the customer can ask the carrier to redirect the parcel through the carrier's tracking page, and a redirect fee set by the carrier may apply.
2. Address change requests are accepted only from the email address on the customer record. A request from any other address is treated as unverified and goes to a person.
3. The agent cannot change an address itself: the address field is not on the agent's write whitelist. It confirms that the order is still `processing`, records the new address in its hand-off, and sets `needs_human` so that a team member makes the change.
4. Moving an address between the metro and regional zones changes the delivery estimate; the customer is told the new estimate when the change is confirmed.

## 3. Lost or delayed parcels

1. A parcel is considered delayed when it has not arrived 5 business days after the end of its delivery estimate. At that point a team member opens a trace with the carrier.
2. A parcel is considered lost when it has not arrived 10 business days after the end of its delivery estimate, or earlier if the carrier confirms the loss.
3. For a lost parcel the customer chooses either a replacement sent by express at no charge, or a full refund including the original shipping fee.
4. Lost-parcel refunds and replacements are approved by a team member; the agent looks up the order, confirms the dates and hands the case over.

## 4. Missed deliveries and re-delivery

1. The carrier attempts delivery twice. After the second failed attempt the parcel is held at the nearest collection point for 7 calendar days.
2. If the parcel is not collected within those 7 calendar days it is returned to us. Re-dispatching a returned parcel costs the customer a 12.50 AUD re-dispatch fee, which is waived for gold and vip customers.
3. A customer who no longer wants a returned parcel is refunded under the refunds policy, less the original shipping fee.

## 5. International orders

1. We ship outside Australia to New Zealand only.
2. New Zealand deliveries take 7 to 12 business days and are charged a flat 29.95 AUD.
3. Import duties and taxes are paid by the customer to the carrier on delivery; they are not included in the order total and are not refundable.
4. Express shipping and address redirects are not available for New Zealand orders.

## 6. PO boxes and parcel lockers

1. Standard shipping can be delivered to PO boxes and parcel lockers.
2. Express shipping cannot be delivered to PO boxes or parcel lockers; an express order addressed to a PO box is downgraded to standard and the difference in shipping fee is refunded.
3. Parcel-locker deliveries are held for 48 hours before the parcel is returned to the carrier depot.
