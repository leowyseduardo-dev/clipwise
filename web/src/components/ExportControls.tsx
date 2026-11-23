import { useEffect, useState } from "react";
import { getJson, sendJson } from "../lib/api";

export type ExportLook = {
  platform: string;
  sound_accent: boolean;
  logo_id: string;
  transition: string;
  aspect: string;
  caption_font: string;
  caption_color: string;
  accent_color: string;
  music_level: number | null;
  saturation: number;
  brand_text: string;
};
type Preset = ExportLook & {
  subtitle_style: string;
  layout: string;
  remove_silences: boolean;
  dynamic_zoom: boolean;
  context_overlay: boolean;
  title_card_style: string;
  title_card_position: string;
  title_card_seconds: number;
};
type Row = { name: string; settings: Preset };

export function ExportControls({
  value,
  onChange,
}: {
  value: ExportLook;
  onChange: (look: ExportLook) => void;
}) {
  const [logoStatus, setLogoStatus] = useState("");
  function set<K extends keyof ExportLook>(key: K, v: ExportLook[K]) {
    onChange({ ...value, [key]: v });
  }
  return (
    <section className="studio-box">
      <h4>Exportación y marca</h4>
      <div className="studio-grid">
        <label>
          Formato
          <select
            className="field"
            value={value.aspect}
            onChange={(e) => set("aspect", e.target.value)}
          >
            <option>9:16</option>
            <option>1:1</option>
            <option>16:9</option>
          </select>
        </label>
        <label>
          Tipografía
          <select
            className="field"
            value={value.caption_font}
            onChange={(e) => set("caption_font", e.target.value)}
          >
            {[
              "",
              "Arial",
              "Arial Black",
              "Impact",
              "Georgia",
              "Verdana",
              "Tahoma",
            ].map((f) => (
              <option key={f} value={f}>
                {f || "Del estilo"}
              </option>
            ))}
          </select>
        </label>
        <label>
          Color de texto
          <input
            type="color"
            value={value.caption_color || "#ffffff"}
            onChange={(e) => set("caption_color", e.target.value)}
          />
        </label>
        <label>
          Palabra resaltada
          <input
            type="color"
            value={value.accent_color || "#ffd700"}
            onChange={(e) => set("accent_color", e.target.value)}
          />
        </label>
        <label>
          Área segura
          <select
            className="field"
            value={value.platform}
            onChange={(e) => set("platform", e.target.value)}
          >
            {Object.entries({
              universal: "General",
              tiktok: "TikTok",
              shorts: "YouTube Shorts",
              instagram: "Instagram Reels",
              facebook: "Facebook Reels",
            }).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={value.sound_accent}
            onChange={(e) => set("sound_accent", e.target.checked)}
          />{" "}
          Acento sonoro al abrir
        </label>
        <label>
          Transición
          <select
            className="field"
            value={value.transition}
            onChange={(e) => set("transition", e.target.value)}
          >
            <option value="cut">Corte directo</option>
            <option value="fade">Fundido de entrada y salida</option>
          </select>
        </label>
        <label>
          Logotipo PNG
          <input
            type="file"
            accept="image/png"
            onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              const form = new FormData();
              form.append("file", f);
              try {
                const res = await fetch("/api/studio/logo", {
                  method: "POST",
                  body: form,
                });
                const body = await res.json();
                if (!res.ok) throw Error(body.detail);
                set("logo_id", body.logo_id);
                setLogoStatus("Logo cargado.");
              } catch (err) {
                setLogoStatus(
                  err instanceof Error ? err.message : "Error al subir el PNG.",
                );
              }
            }}
          />
          {value.logo_id && (
            <button
              type="button"
              className="button-ghost"
              onClick={() => {
                set("logo_id", "");
                setLogoStatus("");
              }}
            >
              Quitar logo
            </button>
          )}
          <small role="status">{logoStatus}</small>
        </label>
        <label>
          Marca de texto
          <input
            className="field"
            maxLength={48}
            value={value.brand_text}
            onChange={(e) => set("brand_text", e.target.value)}
          />
        </label>
        <label>
          Saturación · {value.saturation.toFixed(1)}
          <input
            type="range"
            min="0"
            max="2"
            step=".1"
            value={value.saturation}
            onChange={(e) => set("saturation", Number(e.target.value))}
          />
        </label>
        <label>
          Música adjunta ·{" "}
          {value.music_level === null
            ? "predeterminada"
            : Math.round(value.music_level * 100) + "%"}
          <input
            type="range"
            min="0"
            max="1"
            step=".01"
            value={value.music_level ?? 0.14}
            onChange={(e) => set("music_level", Number(e.target.value))}
          />
        </label>
      </div>
    </section>
  );
}

export function PresetControls({
  settings,
  apply,
}: {
  settings: Preset;
  apply: (p: Preset) => void;
}) {
  const [rows, setRows] = useState<Row[]>([]),
    [name, setName] = useState(""),
    [notice, setNotice] = useState("");
  useEffect(() => {
    getJson<Row[]>("/api/studio/presets")
      .then(setRows)
      .catch((e) => setNotice(e.message));
  }, []);
  async function save() {
    try {
      setRows(
        await sendJson("/api/studio/presets", "PUT", {
          name: name.trim(),
          settings,
        }),
      );
      setNotice("Estilo guardado.");
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Error al guardar.");
    }
  }
  return (
    <section className="studio-box">
      <h4>Estilos guardados</h4>
      <div className="studio-actions">
        <label>
          Nombre
          <input
            className="field"
            maxLength={64}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <button
          type="button"
          className="button-ghost"
          disabled={!name.trim()}
          onClick={save}
        >
          Guardar estilo
        </button>
        {rows.map((r) => (
          <button
            type="button"
            className="button-ghost"
            key={r.name}
            onClick={() => {
              apply(r.settings);
              setName(r.name);
              setNotice("Estilo cargado. Pulsa Aplicar para renderizar.");
            }}
          >
            {r.name}
          </button>
        ))}
      </div>
      {notice && <p role="status">{notice}</p>}
    </section>
  );
}
