import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { Toaster, toast } from "sonner";
import {
  Flame, Search, Loader2, Lock, Ban, Copy, Download, ChevronRight,
  Sparkles, ShieldAlert, Zap, Wand2, BookOpen, TestTube2, CheckCircle2,
  XCircle, AlertTriangle, ListTree, BarChart3, Layers, Coins, Beaker, GitCompareArrows,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Radar, RadarChart,
  PolarGrid, PolarAngleAxis, PolarRadiusAxis, Cell, Tooltip as RTooltip,
} from "recharts";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Textarea } from "./components/ui/textarea";
import { Switch } from "./components/ui/switch";
import { Slider } from "./components/ui/slider";
import { Badge } from "./components/ui/badge";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "./components/ui/hover-card";
import "./index.css";

const API_BASE = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
const API = `${API_BASE}/api`;

const MODES = [
  { id: "best", label: "Best Possible", desc: "Strongest realistic build, no budget cap" },
  { id: "optimized", label: "Optimized", desc: "Powerful, focused, highly synergistic" },
  { id: "br3", label: "BR3", desc: "Optimized-but-fair table" },
  { id: "br4", label: "BR4 / High Power", desc: "Tutors, fast mana, compact combos" },
  { id: "cedh", label: "cEDH", desc: "Competitive staples & interaction" },
  { id: "budget", label: "Budget", desc: "Strongest deck under a price cap" },
  { id: "theme", label: "Theme", desc: "Tribal, artifacts, aristocrats, etc." },
];

const TOGGLES = [
  ["no_two_card_combos", "Disable two-card infinites"],
  ["no_fast_mana", "Disable fast mana"],
  ["no_tutors", "Disable tutors"],
  ["no_mld", "Disable mass land destruction"],
  ["no_stax", "Disable stax"],
  ["no_extra_turns", "Disable extra turns"],
  ["no_theft", "Disable theft effects"],
];

const TABS = [
  ["decklist", "Decklist", ListTree],
  ["strategy", "Strategy", BookOpen],
  ["quality", "Quality", Sparkles],
  ["categories", "Categories", Layers],
  ["curve", "Mana Curve", BarChart3],
  ["combos", "Combos", Zap],
  ["nonbos", "Nonbos", ShieldAlert],
  ["prices", "Prices", Coins],
  ["simulation", "Simulation", Beaker],
  ["validation", "Validation", CheckCircle2],
  ["export", "Export", Download],
];

function ManaCost({ cost }) {
  if (!cost) return null;
  const syms = cost.match(/\{[^}]+\}/g) || [];
  return (
    <span className="inline-flex items-center gap-[1px] align-middle">
      {syms.map((s, i) => {
        const c = s.replace(/[{}]/g, "");
        const cls = ["W", "U", "B", "R", "G", "C"].includes(c) ? `pip-${c}` : "pip-C";
        return <span key={i} className={`mana-pip ${cls}`}>{c}</span>;
      })}
    </span>
  );
}

function CardName({ card, className }) {
  return (
    <HoverCard openDelay={120} closeDelay={40}>
      <HoverCardTrigger asChild>
        <span className={`block cursor-default transition-colors duration-200 hover:text-primary ${className || ""}`}>{card.name}</span>
      </HoverCardTrigger>
      {card.image && (
        <HoverCardContent side="right" className="w-[240px] p-0 border-border bg-transparent shadow-2xl">
          <img src={card.image} alt={card.name} className="w-full rounded-lg" />
        </HoverCardContent>
      )}
    </HoverCard>
  );
}

export default function App() {
  const [tab, setTab] = useState("build");
  const [query, setQuery] = useState("");
  const [sugs, setSugs] = useState([]);
  const [commander, setCommander] = useState(null);
  const [mode, setMode] = useState("optimized");
  const [budget, setBudget] = useState("");
  const [maxCard, setMaxCard] = useState("");
  const [landCount, setLandCount] = useState(34);
  const [theme, setTheme] = useState("");
  const [toggles, setToggles] = useState({});
  const [locks, setLocks] = useState("");
  const [excludes, setExcludes] = useState("");
  const [bans, setBans] = useState("");
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState("");
  const [deck, setDeck] = useState(null);
  const [rtab, setRtab] = useState("decklist");
  const debounce = useRef();

  useEffect(() => {
    if (query.length < 2 || (commander && commander.name === query)) { setSugs([]); return; }
    clearTimeout(debounce.current);
    debounce.current = setTimeout(async () => {
      try {
        const r = await axios.get(`${API}/commanders/search`, { params: { q: query } });
        setSugs(r.data.results);
      } catch (e) { /* ignore */ }
    }, 220);
  }, [query]); // eslint-disable-line

  const pickCommander = async (name) => {
    setSugs([]); setQuery(name);
    try {
      const r = await axios.get(`${API}/card`, { params: { name } });
      setCommander(r.data);
      toast.success(`${r.data.name} loaded`);
    } catch (e) { toast.error("Could not load commander"); }
  };

  const cycle = ["Analyzing commander...", "Ranking archetypes...", "Building packages...",
    "Adding ramp & interaction...", "Assembling mana base...", "Scanning combos & nonbos...",
    "Running simulations...", "Validating deck..."];

  const generate = async () => {
    if (!commander) { toast.error("Select a commander first"); return; }
    setLoading(true); setDeck(null); setProgress(cycle[0]);
    const toList = (s) => s.split(/[\n,]/).map((x) => x.trim()).filter(Boolean);
    try {
      const start = await axios.post(`${API}/generate`, {
        commander: commander.name, mode, theme: theme || null,
        budget: budget ? parseFloat(budget) : null,
        max_price_per_card: maxCard ? parseFloat(maxCard) : null,
        land_count: landCount, locks: toList(locks), excludes: toList(excludes),
        local_bans: toList(bans), toggles, seed: null,
      });
      if (start.data.result) {
        setDeck(start.data.result); setRtab("decklist"); setLoading(false); setProgress("");
        toast.success(`Deck generated — ${start.data.result.count} cards`);
        return;
      }
      if (start.data.status === "error") {
        throw new Error(start.data.error || "Generation failed");
      }
      const jobId = start.data.job_id;
      const poll = async () => {
        const r = await axios.get(`${API}/generate/status/${jobId}`);
        if (r.data.progress) setProgress(r.data.progress);
        if (r.data.status === "done") {
          setDeck(r.data.result); setRtab("decklist"); setLoading(false); setProgress("");
          toast.success(`Deck generated — ${r.data.result.count} cards`);
        } else if (r.data.status === "error") {
          setLoading(false); setProgress("");
          toast.error(r.data.error || "Generation failed");
        } else {
          setTimeout(poll, 1500);
        }
      };
      setTimeout(poll, 1500);
    } catch (e) {
      setLoading(false); setProgress("");
      toast.error(e.response?.data?.detail || e.message || "Generation failed");
    }
  };

  return (
    <div className="relative min-h-screen" style={{ zIndex: 1 }}>
      <Toaster theme="dark" position="top-right" richColors />
      <header className="glass sticky top-0 z-30 flex items-center justify-between gap-3 px-4 py-3 sm:px-6 sm:py-4">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          <div className="w-10 h-10 rounded flex items-center justify-center bg-primary/15 border border-primary/30">
            <Flame className="w-5 h-5 text-primary" />
          </div>
          <div className="min-w-0">
            <h1 className="font-display text-lg font-extrabold leading-tight tracking-tighter sm:text-2xl sm:leading-none">Commander Forge <span className="text-primary">AI</span></h1>
            <p className="mt-1 hidden font-mono-data text-[10px] uppercase tracking-[0.25em] text-muted-foreground sm:block">Deterministic EDH deck architect</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1 sm:gap-2">
          <TopTab id="build" cur={tab} set={setTab} icon={Wand2} label="Build" />
          <TopTab id="improve" cur={tab} set={setTab} icon={GitCompareArrows} label="Improve" />
        </div>
      </header>

      <main className="p-6 max-w-[1500px] mx-auto">
        {tab === "build" ? (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            <section className="lg:col-span-4 space-y-4">
              <BuilderPanel {...{ query, setQuery, sugs, pickCommander, commander, mode, setMode,
                budget, setBudget, maxCard, setMaxCard, landCount, setLandCount, theme, setTheme,
                toggles, setToggles, locks, setLocks, excludes, setExcludes, bans, setBans,
                loading, progress, generate }} />
            </section>
            <section className="lg:col-span-8">
              {!deck && !loading && <EmptyState />}
              {loading && <GeneratingState progress={progress} />}
              {deck && <Results deck={deck} rtab={rtab} setRtab={setRtab} />}
            </section>
          </div>
        ) : (
          <ImproveView />
        )}
      </main>
    </div>
  );
}

function TopTab({ id, cur, set, icon: Icon, label }) {
  const active = cur === id;
  return (
    <button data-testid={`toptab-${id}`} onClick={() => set(id)}
      className={`flex h-11 items-center gap-2 rounded border px-2.5 text-sm font-medium transition-colors duration-200 sm:px-4 ${active ? "bg-primary/15 border-primary/40 text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
      <Icon className="w-4 h-4" /> <span className="hidden sm:inline">{label}</span><span className="sr-only sm:hidden">{label}</span>
    </button>
  );
}

function Field({ label, children }) {
  return (
    <div className="space-y-1.5">
      <label className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-mono-data">{label}</label>
      {children}
    </div>
  );
}

function BuilderPanel(p) {
  return (
    <div className="glass rounded-lg p-5 space-y-5 fadeup">
      <Field label="Commander">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input data-testid="commander-search" value={p.query} placeholder="Search a commander..."
            onChange={(e) => p.setQuery(e.target.value)} className="h-11 border-border bg-card pl-9" />
          {p.sugs.length > 0 && (
            <div className="absolute z-40 mt-1 w-full glass rounded-md overflow-hidden border border-border">
              {p.sugs.map((s) => (
                <button key={s} data-testid="commander-suggestion" onClick={() => p.pickCommander(s)}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-primary/10 transition-colors duration-150 flex items-center gap-2">
                  <ChevronRight className="w-3 h-3 text-primary" />{s}
                </button>
              ))}
            </div>
          )}
        </div>
      </Field>

      {p.commander && (
        <div className="flex gap-3 fadeup" data-testid="selected-commander">
          {p.commander.image && <img src={p.commander.image} alt="" className="w-24 rounded-md border border-border" />}
          <div className="flex-1 min-w-0">
            <div className="font-display font-bold text-base leading-tight">{p.commander.name}</div>
            <div className="text-xs text-muted-foreground mt-0.5">{p.commander.type}</div>
            <div className="mt-1"><ManaCost cost={p.commander.mana_cost} /></div>
            <div className="flex gap-1 mt-2 flex-wrap">
              {(p.commander.color_identity.length ? p.commander.color_identity : ["C"]).map((c) => (
                <span key={c} className={`mana-pip pip-${c}`}>{c}</span>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground mt-2 line-clamp-4 leading-snug">{p.commander.oracle}</p>
          </div>
        </div>
      )}

      <Field label="Power Mode">
        <div className="grid grid-cols-2 gap-1.5">
          {MODES.map((m) => (
            <button key={m.id} data-testid={`mode-${m.id}`} onClick={() => p.setMode(m.id)} title={m.desc}
              className={`${m.id === "theme" ? "col-span-2" : ""} min-h-11 rounded border px-3 py-2 text-left text-xs transition-colors duration-200 ${p.mode === m.id ? "bg-primary/15 border-primary/50 text-primary" : "border-border text-muted-foreground hover:text-foreground"}`}>
              <div className="font-semibold">{m.label}</div>
            </button>
          ))}
        </div>
      </Field>

      {p.mode === "theme" && (
        <Field label="Theme">
          <Input data-testid="theme-input" value={p.theme} onChange={(e) => p.setTheme(e.target.value)}
            placeholder="goblin, artifacts, aristocrats..." className="bg-card" />
        </Field>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Field label="Budget ($)">
          <Input data-testid="budget-input" type="number" value={p.budget} onChange={(e) => p.setBudget(e.target.value)} placeholder="none" className="bg-card font-mono-data" />
        </Field>
        <Field label="Max $/card">
          <Input data-testid="maxcard-input" type="number" value={p.maxCard} onChange={(e) => p.setMaxCard(e.target.value)} placeholder="none" className="bg-card font-mono-data" />
        </Field>
      </div>

      <Field label={`Land Count — ${p.landCount}`}>
        <Slider data-testid="land-slider" min={28} max={42} step={1} value={[p.landCount]}
          onValueChange={(v) => p.setLandCount(v[0])} />
      </Field>

      <Field label="Social Rules">
        <div className="space-y-1.5">
          {TOGGLES.map(([k, lbl]) => (
            <label key={k} htmlFor={`toggle-${k}`} className="flex min-h-11 cursor-pointer items-center justify-between rounded border border-transparent px-3 transition-colors hover:border-border hover:bg-card/60">
              <span className="text-sm text-muted-foreground">{lbl}</span>
              <Switch id={`toggle-${k}`} data-testid={`toggle-${k}`} checked={!!p.toggles[k]}
                onCheckedChange={(v) => p.setToggles((t) => ({ ...t, [k]: v }))} />
            </label>
          ))}
        </div>
      </Field>

      <div className="grid grid-cols-1 gap-3">
        <Field label="Locked cards (one per line)">
          <Textarea data-testid="locks-input" value={p.locks} onChange={(e) => p.setLocks(e.target.value)} rows={2} className="bg-card text-xs font-mono-data" placeholder="Cards to always include" />
        </Field>
        <Field label="Excluded cards">
          <Textarea data-testid="excludes-input" value={p.excludes} onChange={(e) => p.setExcludes(e.target.value)} rows={2} className="bg-card text-xs font-mono-data" />
        </Field>
        <Field label="Local ban list">
          <Textarea data-testid="bans-input" value={p.bans} onChange={(e) => p.setBans(e.target.value)} rows={2} className="bg-card text-xs font-mono-data" placeholder="Dockside Extortionist..." />
        </Field>
      </div>

      <Button data-testid="generate-deck-btn" onClick={p.generate} disabled={p.loading || !p.commander}
        className={`w-full h-12 text-base font-bold rounded ${p.loading ? "tracing-beam text-white" : "bg-primary hover:bg-primary/90 text-white"}`}>
        {p.loading ? <><Loader2 className="w-5 h-5 animate-spin mr-2" />{p.progress}</> : <><Flame className="w-5 h-5 mr-2" />Forge Deck</>}
      </Button>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="glass flex min-h-[320px] h-full flex-col justify-center rounded-lg p-8 text-left fadeup sm:p-10">
      <div className="max-w-md">
        <p className="font-mono-data text-[10px] uppercase tracking-[0.2em] text-primary">Deck builder</p>
        <h2 className="mt-2 font-display text-3xl font-bold tracking-tighter">Start with a commander.</h2>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">Search for a commander on the left, then tune power, budget, and table rules before forging your deck.</p>
        <div className="mt-6 flex flex-wrap gap-2 text-xs text-muted-foreground">
          <span className="rounded border border-border px-3 py-2">100-card validation</span>
          <span className="rounded border border-border px-3 py-2">Combo analysis</span>
          <span className="rounded border border-border px-3 py-2">Moxfield export</span>
        </div>
      </div>
    </div>
  );
}

function GeneratingState({ progress }) {
  return (
    <div className="glass rounded-lg h-full min-h-[400px] flex flex-col items-center justify-center text-center p-10">
      <Loader2 className="w-10 h-10 text-primary animate-spin mb-5" />
      <div className="font-mono-data text-sm text-primary tracking-wide">{progress}</div>
      <div className="text-xs text-muted-foreground mt-2">Querying Scryfall & scoring cards...</div>
    </div>
  );
}

function Results({ deck, rtab, setRtab }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-[180px_1fr] gap-4 fadeup">
      <nav className="glass rounded-lg p-2 h-max md:sticky md:top-24 space-y-0.5">
        {TABS.map(([id, label, Icon]) => (
          <button key={id} data-testid={`rtab-${id}`} onClick={() => setRtab(id)}
            className={`w-full flex items-center gap-2 px-3 py-2 rounded text-xs font-medium border-l-2 transition-colors duration-200 ${rtab === id ? "border-primary bg-primary/10 text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            <Icon className="w-4 h-4" /> {label}
            {id === "combos" && deck.combos.included.length > 0 && <span className="ml-auto text-[10px] font-mono-data text-accent">{deck.combos.included.length}</span>}
            {id === "nonbos" && deck.nonbos.length > 0 && <span className="ml-auto text-[10px] font-mono-data text-yellow-500">{deck.nonbos.length}</span>}
          </button>
        ))}
      </nav>
      <div className="min-w-0">
        <DeckHeader deck={deck} />
        <div className="mt-4">
          {rtab === "decklist" && <Decklist deck={deck} />}
          {rtab === "strategy" && <Strategy deck={deck} />}
          {rtab === "quality" && <Quality deck={deck} />}
          {rtab === "categories" && <Categories deck={deck} />}
          {rtab === "curve" && <Curve deck={deck} />}
          {rtab === "combos" && <Combos deck={deck} />}
          {rtab === "nonbos" && <Nonbos deck={deck} />}
          {rtab === "prices" && <Prices deck={deck} />}
          {rtab === "simulation" && <Simulation deck={deck} />}
          {rtab === "validation" && <Validation deck={deck} />}
          {rtab === "export" && <Export deck={deck} />}
        </div>
      </div>
    </div>
  );
}

function DeckHeader({ deck }) {
  return (
    <div className="glass rounded-lg p-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-mono-data">{deck.commander.name}</div>
          <h2 className="font-display text-2xl font-bold tracking-tight">{deck.archetype}</h2>
        </div>
        <div className="flex items-center gap-4 font-mono-data text-sm">
          <Stat label="Cards" value={deck.count} ok={deck.count === 100} />
          <Stat label="Lands" value={deck.categories.Lands || 0} />
          <Stat label="Price" value={`$${deck.total_price}`} />
          <Stat label="Valid" value={deck.validation.valid ? "PASS" : "FAIL"} ok={deck.validation.valid} bad={!deck.validation.valid} />
        </div>
      </div>
      {deck.warnings.length > 0 && (
        <div className="mt-3 space-y-1">
          {deck.warnings.map((w, i) => (
            <div key={i} data-testid="power-warning" className={`text-xs flex items-center gap-2 ${w.level === "high" ? "text-red-400" : "text-yellow-500"}`}>
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" /> {w.text}
            </div>
          ))}
        </div>
      )}
      {!deck.ai_used && (
        <div className="mt-2 text-[11px] text-secondary flex items-center gap-1.5">
          <Sparkles className="w-3 h-3" /> Deterministic mode (AI request was rate-limited or quota exhausted; check OpenAI billing/usage to enable AI strategy & primers).
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, ok, bad }) {
  return (
    <div className="text-right">
      <div className={`font-bold ${ok ? "text-green-400" : bad ? "text-red-400" : ""}`}>{value}</div>
      <div className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div>
    </div>
  );
}

const CATCOLORS = { Ramp: "text-green-400", "Card Draw": "text-blue-400", Removal: "text-red-400",
  "Board Wipe": "text-red-500", Counterspell: "text-blue-500", Tutor: "text-purple-400",
  Lands: "text-amber-400", "Fast Mana": "text-orange-400", Stax: "text-pink-400" };

function Decklist({ deck }) {
  const groups = {};
  deck.cards.forEach((c) => { const g = c.categories[0]; (groups[g] = groups[g] || []).push(c); });
  const order = Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length);
  return (
    <div className="glass rounded-lg overflow-hidden" data-testid="decklist">
      {order.map((g) => (
        <div key={g}>
          <div className="px-4 py-1.5 bg-card/60 border-y border-border flex items-center justify-between">
            <span className={`text-[10px] uppercase tracking-[0.2em] font-mono-data ${CATCOLORS[g] || "text-muted-foreground"}`}>{g}</span>
            <span className="text-[10px] font-mono-data text-muted-foreground">{groups[g].length}</span>
          </div>
          {groups[g].map((c, i) => (
            <motion.div key={c.name + i} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: Math.min(i * 0.01, 0.3) }}
              data-testid="card-row" className="flex items-center gap-2 px-4 py-1.5 border-b border-border/40 hover:bg-primary/5 transition-colors duration-150 text-sm">
              <div className="w-24 shrink-0 overflow-hidden"><ManaCost cost={c.mana_cost} /></div>
              <CardName card={c} className="font-medium min-w-0 truncate flex-1" />
              {c.in_synergy && <Sparkles className="w-3 h-3 text-accent shrink-0" title="Synergy core" />}
              <span className="hidden md:block text-[11px] text-muted-foreground truncate max-w-[280px] flex-1" title={c.reason}>{c.reason}</span>
              <span className="font-mono-data text-xs text-secondary w-14 text-right shrink-0">{c.price ? `$${c.price}` : "—"}</span>
              <span className="font-mono-data text-xs w-10 text-right shrink-0 text-primary">{c.score}</span>
            </motion.div>
          ))}
        </div>
      ))}
    </div>
  );
}

function Strategy({ deck }) {
  return (
    <div className="space-y-4">
      <div className="glass rounded-lg p-5">
        <h3 className="font-display text-xl font-bold mb-1">Primary Strategy</h3>
        <p className="text-sm text-muted-foreground leading-relaxed">{deck.strategy}</p>
        {deck.secondary && <><h3 className="font-display text-lg font-bold mt-4 mb-1">Secondary Plan</h3><p className="text-sm text-muted-foreground">{deck.secondary}</p></>}
        <div className="mt-4 flex flex-wrap gap-2">
          {deck.wincons.map((w, i) => <Badge key={i} className="bg-accent/15 text-accent border-accent/30">{w}</Badge>)}
        </div>
      </div>
      <div className="glass rounded-lg p-5">
        <h3 className="font-display text-xl font-bold mb-3 flex items-center gap-2"><BookOpen className="w-5 h-5 text-primary" />Deck Primer</h3>
        <Markdownish text={deck.primer} />
      </div>
    </div>
  );
}

function Markdownish({ text }) {
  const lines = (text || "").split("\n");
  return (
    <div className="text-sm text-muted-foreground space-y-1.5 leading-relaxed">
      {lines.map((l, i) => {
        if (l.startsWith("## ")) return <h4 key={i} className="font-display text-base font-bold text-foreground mt-3">{l.slice(3)}</h4>;
        if (l.startsWith("# ")) return <h4 key={i} className="font-display text-lg font-bold text-foreground mt-3">{l.slice(2)}</h4>;
        if (!l.trim()) return null;
        return <p key={i}>{l.replace(/\*\*/g, "")}</p>;
      })}
    </div>
  );
}

function Quality({ deck }) {
  const data = Object.entries(deck.quality).map(([k, v]) => ({ metric: k, score: v.score }));
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className="glass rounded-lg p-4">
        <ResponsiveContainer width="100%" height={340}>
          <RadarChart data={data}>
            <PolarGrid stroke="#27272a" />
            <PolarAngleAxis dataKey="metric" tick={{ fill: "#a1a1aa", fontSize: 9, fontFamily: "JetBrains Mono" }} />
            <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
            <Radar dataKey="score" stroke="#ea580c" fill="#ea580c" fillOpacity={0.35} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <div className="glass rounded-lg divide-y divide-border/40" data-testid="quality-scores">
        {Object.entries(deck.quality).map(([k, v]) => (
          <div key={k} className="px-4 py-2">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">{k}</span>
              <span className="font-mono-data text-primary">{v.score}</span>
            </div>
            <div className="h-1 bg-card rounded mt-1 overflow-hidden"><div className="h-full bg-primary" style={{ width: `${v.score}%` }} /></div>
            <div className="text-[11px] text-muted-foreground mt-1">{v.evidence}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Categories({ deck }) {
  return (
    <div className="glass rounded-lg p-5">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {Object.entries(deck.categories).map(([k, v]) => (
          <div key={k} className="border border-border/40 rounded p-3">
            <div className="font-mono-data text-2xl font-bold text-primary">{v}</div>
            <div className={`text-xs mt-1 ${CATCOLORS[k] || "text-muted-foreground"}`}>{k}</div>
          </div>
        ))}
      </div>
      <h3 className="font-display text-lg font-bold mt-6 mb-3">Card Types</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {Object.entries(deck.types).map(([k, v]) => (
          <div key={k} className="flex items-center justify-between border-b border-border/40 py-1 text-sm">
            <span className="text-muted-foreground">{k}</span><span className="font-mono-data">{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Curve({ deck }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className="glass rounded-lg p-4">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-mono-data mb-3">Mana Curve (nonland)</div>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={deck.curve}>
            <XAxis dataKey="cmc" tick={{ fill: "#a1a1aa", fontSize: 11, fontFamily: "JetBrains Mono" }} />
            <YAxis tick={{ fill: "#a1a1aa", fontSize: 11 }} />
            <RTooltip contentStyle={{ background: "#121214", border: "1px solid #27272a", fontFamily: "JetBrains Mono", fontSize: 12 }} />
            <Bar dataKey="count" radius={[3, 3, 0, 0]}>
              {deck.curve.map((e, i) => <Cell key={i} fill="#ea580c" />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="glass rounded-lg p-4">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-mono-data mb-3">Colored Mana Sources</div>
        <div className="space-y-3 mt-4">
          {deck.sources.map((s) => (
            <div key={s.color} className="flex items-center gap-3">
              <span className={`mana-pip pip-${s.color}`}>{s.color}</span>
              <div className="flex-1 h-3 bg-card rounded overflow-hidden">
                <div className="h-full bg-secondary" style={{ width: `${Math.min(100, s.count * 4)}%` }} />
              </div>
              <span className="font-mono-data text-sm w-8 text-right">{s.count}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Combos({ deck }) {
  const c = deck.combos;
  return (
    <div className="space-y-3" data-testid="combos-panel">
      <div className="text-xs text-muted-foreground">Source: <span className="font-mono-data text-secondary">{c.source}</span>{c.removed_two_card && <span className="text-yellow-500"> · Removed {c.removed_two_card.length} two-card combo(s): {c.removed_two_card.join(", ")}</span>}</div>
      {c.included.length === 0 && <div className="glass rounded-lg p-6 text-center text-muted-foreground text-sm">No combos detected in this list.</div>}
      {c.included.map((combo, i) => (
        <div key={i} className="glass rounded-lg p-4 border-l-2 border-accent">
          <div className="flex items-center gap-2 flex-wrap">
            {combo.cards.map((n) => <Badge key={n} className="bg-accent/15 text-accent border-accent/30">{n}</Badge>)}
            <Badge className="ml-auto bg-card border-border text-muted-foreground font-mono-data text-[10px]">{combo.kind}</Badge>
          </div>
          {combo.result && <div className="text-sm mt-2 text-foreground">→ {combo.result}</div>}
          {combo.steps && <div className="text-[11px] text-muted-foreground mt-1 leading-snug">{combo.steps}</div>}
        </div>
      ))}
      {c.almost && c.almost.length > 0 && (
        <div className="glass rounded-lg p-4">
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-mono-data mb-2">Near-combos (one piece missing)</div>
          {c.almost.map((a, i) => (
            <div key={i} className="text-xs text-muted-foreground py-1 border-b border-border/40">{a.cards.join(" + ")} — <span className="text-yellow-500">missing {(a.missing || []).join(", ")}</span></div>
          ))}
        </div>
      )}
    </div>
  );
}

const SEVCOLOR = { Critical: "text-red-500 border-red-500", Significant: "text-orange-400 border-orange-400", Situational: "text-yellow-500 border-yellow-500", Acceptable: "text-muted-foreground border-border" };

function Nonbos({ deck }) {
  return (
    <div className="space-y-2" data-testid="nonbos-panel">
      {deck.nonbos.length === 0 && <div className="glass rounded-lg p-6 text-center text-muted-foreground text-sm">No significant nonbos detected.</div>}
      {deck.nonbos.map((n, i) => (
        <div key={i} className={`glass rounded-lg p-4 border-l-2 ${SEVCOLOR[n.severity] || "border-border"}`}>
          <div className="flex items-center justify-between">
            <span className="font-semibold text-sm">{n.card}</span>
            <Badge className={`bg-transparent ${SEVCOLOR[n.severity]}`}>{n.severity}</Badge>
          </div>
          <div className="text-xs text-muted-foreground mt-1">{n.message}</div>
        </div>
      ))}
    </div>
  );
}

function Prices({ deck }) {
  const priced = [...deck.cards].filter((c) => c.price).sort((a, b) => b.price - a.price);
  return (
    <div className="glass rounded-lg overflow-hidden">
      <div className="px-4 py-2 flex justify-between border-b border-border bg-card/60">
        <span className="text-[10px] uppercase tracking-[0.2em] font-mono-data text-muted-foreground">Most Expensive</span>
        <span className="font-mono-data text-sm text-secondary">Total ${deck.total_price}</span>
      </div>
      {priced.slice(0, 30).map((c, i) => (
        <div key={i} className="flex justify-between px-4 py-1.5 border-b border-border/40 text-sm">
          <CardName card={c} /><span className="font-mono-data text-secondary">${c.price}</span>
        </div>
      ))}
    </div>
  );
}

function Simulation({ deck }) {
  const s = deck.simulation;
  const items = [["Keepable hands", `${s.keepable_pct}%`], ["Mulligan rate", `${s.mulligan_pct}%`],
    ["Avg lands / hand", s.avg_lands], ["Ramp in opener", `${s.ramp_in_hand_pct}%`],
    ["Mana screw risk", `${s.screw_pct}%`], ["Flood risk", `${s.flood_pct}%`],
    ["Total lands", s.total_lands], ["Mana sources", s.total_mana_sources]];
  return (
    <div className="glass rounded-lg p-5" data-testid="simulation-panel">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {items.map(([k, v]) => (
          <div key={k} className="border border-border/40 rounded p-3">
            <div className="font-mono-data text-2xl font-bold text-primary">{v}</div>
            <div className="text-[11px] text-muted-foreground mt-1">{k}</div>
          </div>
        ))}
      </div>
      <div className="text-[11px] text-muted-foreground mt-4">n = {s.trials} Monte Carlo trials. {s.assumptions}</div>
    </div>
  );
}

function Validation({ deck }) {
  const v = deck.validation;
  return (
    <div className="glass rounded-lg p-5" data-testid="validation-panel">
      <div className={`flex items-center gap-2 text-lg font-display font-bold ${v.valid ? "text-green-400" : "text-red-400"}`}>
        {v.valid ? <CheckCircle2 className="w-6 h-6" /> : <XCircle className="w-6 h-6" />}
        {v.valid ? "Deck is legal & valid" : "Validation issues found"}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mt-4">
        {Object.entries(v.checks).map(([k, val]) => (
          <div key={k} className="flex items-center gap-2 text-sm">
            {val === false ? <XCircle className="w-4 h-4 text-red-400" /> : <CheckCircle2 className="w-4 h-4 text-green-400" />}
            <span className="text-muted-foreground">{k}</span>
            <span className="ml-auto font-mono-data text-xs">{String(val)}</span>
          </div>
        ))}
      </div>
      {v.issues.length > 0 && <ul className="mt-4 space-y-1 text-sm text-red-400">{v.issues.map((x, i) => <li key={i}>• {x}</li>)}</ul>}
    </div>
  );
}

function Export({ deck }) {
  const [fmt, setFmt] = useState("moxfield");
  const text = fmt === "moxfield" ? deck.moxfield
    : fmt === "json" ? JSON.stringify(deck.cards.map((c) => ({ name: c.name, category: c.categories[0], price: c.price })), null, 2)
    : ["name,category,mana_value,price,score", ...deck.cards.map((c) => `"${c.name}",${c.categories[0]},${c.cmc},${c.price || 0},${c.score}`)].join("\n");
  const copy = () => { navigator.clipboard.writeText(text); toast.success("Copied to clipboard"); };
  const dl = () => {
    const blob = new Blob([text], { type: "text/plain" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `${deck.commander.name}.${fmt === "json" ? "json" : fmt === "csv" ? "csv" : "txt"}`; a.click();
    toast.success("Downloaded");
  };
  return (
    <div className="glass rounded-lg p-5" data-testid="export-panel">
      <div className="flex items-center gap-2 mb-3">
        {["moxfield", "json", "csv"].map((f) => (
          <button key={f} data-testid={`export-${f}`} onClick={() => setFmt(f)}
            className={`px-3 py-1.5 rounded text-xs font-mono-data border transition-colors duration-200 ${fmt === f ? "bg-primary/15 border-primary/40 text-primary" : "border-border text-muted-foreground"}`}>{f.toUpperCase()}</button>
        ))}
        <div className="ml-auto flex gap-2">
          <Button data-testid="copy-btn" onClick={copy} variant="outline" className="h-8 text-xs border-border"><Copy className="w-3.5 h-3.5 mr-1" />Copy</Button>
          <Button data-testid="download-btn" onClick={dl} className="h-8 text-xs bg-primary text-white"><Download className="w-3.5 h-3.5 mr-1" />Download</Button>
        </div>
      </div>
      <pre className="bg-card rounded p-4 text-xs font-mono-data overflow-auto max-h-[500px] whitespace-pre-wrap">{text}</pre>
    </div>
  );
}

function ImproveView() {
  const [text, setText] = useState("");
  const [cmd, setCmd] = useState("");
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState(null);
  const run = async () => {
    if (!text.trim()) { toast.error("Paste a decklist first"); return; }
    setLoading(true); setRes(null);
    try {
      const r = await axios.post(`${API}/improve`, { decklist: text, commander: cmd || null });
      setRes(r.data); toast.success("Analysis complete");
    } catch (e) { toast.error(e.response?.data?.detail || "Analysis failed"); }
    finally { setLoading(false); }
  };
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className="glass rounded-lg p-5 space-y-3">
        <h2 className="font-display text-xl font-bold">Improve an Existing Deck</h2>
        <Field label="Commander (optional)"><Input data-testid="improve-commander" value={cmd} onChange={(e) => setCmd(e.target.value)} className="bg-card" placeholder="Auto-detected if blank" /></Field>
        <Field label="Decklist (Moxfield / plain text)">
          <Textarea data-testid="improve-decklist" value={text} onChange={(e) => setText(e.target.value)} rows={16} className="bg-card text-xs font-mono-data" placeholder={"1 Sol Ring\n1 Arcane Signet\n1 Command Tower\n..."} />
        </Field>
        <Button data-testid="improve-btn" onClick={run} disabled={loading} className="w-full h-11 bg-primary text-white font-bold">
          {loading ? <><Loader2 className="w-4 h-4 animate-spin mr-2" />Analyzing...</> : <><GitCompareArrows className="w-4 h-4 mr-2" />Analyze Deck</>}
        </Button>
      </div>
      <div>
        {!res && (
          <div className="glass flex min-h-[300px] h-full flex-col justify-center rounded-lg p-8 text-left sm:p-10">
            <p className="font-mono-data text-[10px] uppercase tracking-[0.2em] text-primary">Deck analysis</p>
            <h2 className="mt-2 font-display text-2xl font-bold">Your upgrade plan appears here.</h2>
            <p className="mt-3 max-w-md text-sm leading-6 text-muted-foreground">Paste a decklist to see cuts, adds, combos, nonbos, and a power estimate in one place.</p>
          </div>
        )}
        {res && <ImproveResults res={res} />}
      </div>
    </div>
  );
}

function ImproveResults({ res }) {
  return (
    <div className="space-y-4 fadeup" data-testid="improve-results">
      <div className="glass rounded-lg p-4 flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-mono-data">Power Estimate</div>
          <div className="font-display text-2xl font-bold text-primary">{res.power_estimate.score}/10 <span className="text-sm text-muted-foreground">{res.power_estimate.band}</span></div>
        </div>
        <div className="flex gap-4 font-mono-data text-sm">
          <Stat label="Cards" value={res.total} ok={res.total === 100} bad={res.total !== 100} />
          <Stat label="Lands" value={res.lands} />
          <Stat label="Ramp" value={res.ramp} />
          <Stat label="Draw" value={res.draw} />
          <Stat label="Removal" value={res.removal} />
        </div>
      </div>
      {res.issues.length > 0 && <div className="glass rounded-lg p-4 text-sm text-red-400 space-y-1">{res.issues.map((x, i) => <div key={i}>• {x}</div>)}</div>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="glass rounded-lg p-4">
          <h3 className="font-display font-bold mb-2 text-red-400 flex items-center gap-2"><XCircle className="w-4 h-4" />Recommended Cuts</h3>
          {res.cuts.map((c, i) => <div key={i} className="text-xs py-1.5 border-b border-border/40"><span className="font-medium">{c.card}</span><div className="text-muted-foreground">{c.reason}</div></div>)}
        </div>
        <div className="glass rounded-lg p-4">
          <h3 className="font-display font-bold mb-2 text-green-400 flex items-center gap-2"><CheckCircle2 className="w-4 h-4" />Recommended Adds</h3>
          {res.adds.map((c, i) => <div key={i} className="text-xs py-1.5 border-b border-border/40"><span className="font-medium">{c.card}</span><div className="text-muted-foreground">{c.reason}</div></div>)}
        </div>
      </div>
      {res.combos.included.length > 0 && (
        <div className="glass rounded-lg p-4">
          <h3 className="font-display font-bold mb-2 flex items-center gap-2"><Zap className="w-4 h-4 text-accent" />Combos ({res.combos.included.length})</h3>
          {res.combos.included.map((c, i) => <div key={i} className="text-xs py-1"><span className="text-accent">{c.cards.join(" + ")}</span> → {c.result}</div>)}
        </div>
      )}
    </div>
  );
}
