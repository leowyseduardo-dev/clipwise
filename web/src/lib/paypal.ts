export const PAYPAL_SUPPORT_EMAIL = "support@clipwise.app";

export function paypalLink(base: string, amount: number) {
  return `${base.trim().replace(/\/+$/, "")}/${amount}`;
}
