import Link from "next/link";

export default function Nav() {
  return (
    <nav className="top">
      <Link href="/" className="brand">REVERSA<span>.</span></Link>
      <Link href="/">Overview</Link>
      <Link href="/command">Command</Link>
      <Link href="/recovery">Recovery</Link>
      <Link href="/recovery-race">Recovery Race</Link>
      <Link href="/time-machine">Time Machine</Link>
      <Link href="/connectors">Connectors</Link>
      <Link href="/demo-lab">Demo Lab</Link>
      <Link href="/roi">ROI</Link>
      <Link href="/settings">Settings</Link>
    </nav>
  );
}
