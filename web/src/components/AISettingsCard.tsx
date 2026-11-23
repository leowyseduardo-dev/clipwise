import { useEffect, useState } from "react";
import { getAISettings, saveAISettings, testAIConnection } from "../lib/api";
import type { AIProvider, AISettings } from "../lib/types";

export function AISettingsCard({ onChanged }: { onChanged: (enabled: boolean) => void }) {
  const [config, setConfig] = useState<AISettings | null>(null);
  const [provider, setProvider] = useState<AIProvider>("heuristic");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  function apply(value: AISettings) {
    setConfig(value); setProvider(value.provider); setModel(value.model); setBaseUrl(value.base_url);
    setKey(""); onChanged(value.enabled);
  }
  useEffect(() => {
    let active = true;
    getAISettings().then(value => { if (active) apply(value); })
      .catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, []);
  const preset = config?.providers.find(item => item.id === provider);
  const needsKey = !["heuristic", "ollama"].includes(provider);
  const keySaved = config?.provider === provider && config.base_url === baseUrl && config.key_set;
  function choose(id: AIProvider) {
    const item = config?.providers.find(entry => entry.id === id);
    setProvider(id); setKey(""); setNotice(""); setError("");
    setModel(id === config?.provider ? config.model : item?.model ?? "");
    setBaseUrl(id === config?.provider ? config.base_url : item?.base_url ?? "");
  }
  async function save(probe: boolean, clearKey = false) {
    setBusy(true); setError(""); setNotice("");
    try {
      const saved = await saveAISettings({ provider, model, base_url: baseUrl, api_key: key || undefined, clear_key: clearKey });
      apply(saved);
      if (probe) {
        const result = await testAIConnection();
        if (result.ok) setNotice(result.message); else setError(result.message);
        setConfig(await getAISettings());
      } else setNotice(clearKey ? "Clave eliminada. Se usará el análisis local." : "Configuración guardada para los próximos análisis.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar la configuración.");
    } finally { setBusy(false); }
  }
  return (
    <section className="panel p-6 sm:p-8" aria-label="Configurar inteligencia artificial">
      <p className="eyebrow">IA para momentos, títulos y publicaciones</p>
      <h2 className="mt-1 text-2xl font-semibold tracking-tight">Conecta tu IA</h2>
      <p className="mt-3 max-w-3xl text-sm leading-relaxed text-veru-paper/60">
        El modelo lee fragmentos de la transcripción, evalúa el gancho y el desenlace y revisa los textos del clip.
        El video y el audio se procesan en tu equipo. Si la API falla o agota su cuota, el análisis local continúa.
      </p>
      <fieldset disabled={busy || !config} className="mt-5 space-y-4 disabled:opacity-60">
        <label className="block"><span className="label-xs">Proveedor</span>
          <select className="field mt-2" value={provider} onChange={event => choose(event.target.value as AIProvider)}>
            {config?.providers.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </label>
        <p className="rounded-2xl border border-veru-paper/10 bg-black/20 p-4 text-xs leading-relaxed text-veru-paper/65">{preset?.note || "Cargando proveedores…"}</p>
        {provider !== "heuristic" && <label className="block"><span className="label-xs">Modelo</span>
          <input className="field mt-2" value={model} onChange={event => setModel(event.target.value)} autoComplete="off" />
        </label>}
        {provider === "custom" && <label className="block"><span className="label-xs">Endpoint de la API</span>
          <input type="url" className="field mt-2" value={baseUrl} onChange={event => setBaseUrl(event.target.value)} />
        </label>}
        {needsKey && <label className="block"><span className="label-xs">Clave de API</span>
          <input type="password" className="field mt-2" value={key} onChange={event => setKey(event.target.value)}
            placeholder={keySaved ? "Clave guardada · deja vacío para conservarla" : "Pega aquí tu clave, no en el chat"}
            autoComplete="new-password" spellCheck={false} />
          <span className="mt-2 block text-xs text-veru-paper/45">Se guarda en este equipo, protegida con tu cuenta de Windows. Nunca se muestra al volver a abrir el panel.</span>
        </label>}
        {preset?.key_url && <a href={preset.key_url} target="_blank" rel="noreferrer" className="inline-block text-sm text-veru-blush underline underline-offset-4">
          {provider === "ollama" ? "Obtener Ollama" : "Crear mi clave en la web oficial"} ↗
        </a>}
        {provider === "ollama" && <p className="text-xs text-veru-paper/55">Instala Ollama y descarga el modelo elegido antes de probar la conexión. Clipwise conecta con el servidor local en el puerto 11434.</p>}
        <div className="flex flex-wrap gap-3">
          <button type="button" className="button-primary" onClick={() => void save(true)}>{busy ? "Comprobando…" : "Guardar y probar"}</button>
          <button type="button" className="button-secondary" onClick={() => void save(false)}>Guardar configuración</button>
          {keySaved && <button type="button" className="button-secondary" onClick={() => void save(false, true)}>Eliminar clave</button>}
        </div>
      </fieldset>
      {notice && <p role="status" className="mt-4 text-sm text-emerald-700">{notice}</p>}
      {error && <p role="alert" className="mt-4 text-sm text-amber-700">{error}</p>}
      {!error && config?.last_error && <p className="mt-4 text-xs text-amber-700">{config.last_error}</p>}
      <p className="mt-4 text-xs leading-relaxed text-veru-paper/40">Las APIs gratuitas tienen límites. OpenRouter queda restringido a modelos gratuitos; Gemini requiere mantener tu proyecto en el nivel gratuito. La puntuación estima interés editorial, no garantiza visualizaciones.</p>
    </section>
  );
}
