// Owner: M4. Rules in everyday words. Mirrors fa/release/story.py (plain_cond / RULE_TITLES) so the
// dashboard can describe any rule, including ones the defender adds later, without showing feature names.

export interface Cond { f: string; op: string; v: number }
export interface RuleLike { id: string; action: string; when: Cond[] }

export const RULE_TITLES: Record<string, string> = {
  R1: "A payment much bigger than the customer's usual",
  R2: "A big payment to a brand-new payee",
  R3: "Too many payments in one hour",
  R4: "New device, then money moving",
  R5: "Paying many different people quickly",
  R6: "A large payment at night",
};

const OPS: Record<string, string> = { ">=": "at least", ">": "more than", "<=": "at most", "<": "less than", "==": "exactly" };
const num = (v: number) => (Math.abs(v) < 1e6 ? String(+v.toPrecision(6)) : Math.round(v).toLocaleString("en-IN"));
const rupees = (paise: number) => "₹" + (paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const hours = (h: number) => (h < 1 ? `${Math.round(h * 60)} minutes` : h === 1 ? "1 hour" : `${+h.toFixed(1)} hours`);

export function plainCond(c: Cond): string {
  const op = OPS[c.op] ?? c.op;
  const v = c.v;
  switch (c.f) {
    case "amount_ratio_30d": return `the payment is ${op} ${num(v)}× the customer's usual payment`;
    case "payee_age_h": return `the payee was added ${op} ${hours(v)} ago`;
    case "device_changed_24h": return v ? "the customer is on a device first seen in the last 24 hours" : "the device is not new";
    case "n_pay_1h": return `the customer already made ${op} ${num(v)} payments in the last hour`;
    case "n_pay_24h": return `the customer already made ${op} ${num(v)} payments in the last 24 hours`;
    case "sum_1h": return `the customer already sent ${op} ${rupees(v)} in the last hour`;
    case "sum_24h": return `the customer already sent ${op} ${rupees(v)} in the last 24 hours`;
    case "sum_newpayee_1h": return `${op} ${rupees(v)} went to payees under a day old in the last hour`;
    case "fan_out_1h": return `the customer paid ${op} ${num(v)} different people in the last hour`;
    case "r_fan_in_24h": return `the receiving account got money from ${op} ${num(v)} different senders in the last 24 hours`;
    case "r_passthrough_1h": return `the receiving account forwarded ${op} ${Math.round(v * 100)}% of what it received in the last hour`;
    case "hour_of_day": return `the hour of day is ${op} ${num(v)}`;
    case "night_flag": return v ? "it is night (00:00 to 05:00)" : "it is daytime";
    default: return `${c.f} ${c.op} ${v}`;
  }
}

export const plainRule = (r: RuleLike): string => {
  const verb = r.action === "block" ? "Block the payment" : "Hold the payment for a check";
  return r.when.length ? `${verb} when ${r.when.map(plainCond).join(", AND ")}.` : verb + ".";
};

export const ruleTitle = (r: RuleLike): string => RULE_TITLES[r.id] ?? `New rule ${r.id}`;
