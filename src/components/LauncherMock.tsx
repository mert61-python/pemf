// Author: mertaygn, cglrgrkn
import { CLIENT } from '../config'
import { Bolt } from './Icons'

/* PEMF Vet launcher/dashboard önizlemesi — saf CSS pencere mockup'ı. */
const chrome = { background: 'oklch(14% 0.015 260)' }
const bg = { background: 'oklch(20% 0.02 260)' }
const panel = { background: 'oklch(24% 0.02 260)' }

function Metric({ label, value, tint }: { label: string; value: string; tint: string }) {
  return (
    <div className="rounded-lg border border-white/8 p-3" style={panel}>
      <div className="mb-2 h-1 w-10 rounded-full" style={{ background: tint }} />
      <div className="text-[11px] uppercase tracking-wide text-white/45">{label}</div>
      <div className="mt-0.5 text-lg font-bold text-white/90">{value}</div>
    </div>
  )
}

export default function LauncherMock() {
  return (
    <div className="glow-ring overflow-hidden rounded-xl border border-white/10" style={bg}>
      {/* Başlık çubuğu */}
      <div className="flex items-center gap-2 border-b border-white/8 px-4 py-3" style={chrome}>
        <span className="h-3 w-3 rounded-full" style={{ background: 'oklch(65% 0.2 25)' }} />
        <span className="h-3 w-3 rounded-full" style={{ background: 'oklch(80% 0.15 85)' }} />
        <span className="h-3 w-3 rounded-full" style={{ background: 'oklch(72% 0.17 152)' }} />
        <span className="ml-2 text-xs text-white/45">PEMF Vet Client v{CLIENT.version}</span>
        <span className="ml-auto text-xs text-white/30">Launcher</span>
      </div>

      {/* Gövde */}
      <div className="p-5">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold text-white/90">PEMF Vet Dashboard</div>
            <div className="text-xs text-white/40">Cihaz Durumu: Bağlı Değil</div>
          </div>
          <button className="inline-flex items-center gap-1.5 rounded-md px-4 py-2 text-sm font-semibold text-[oklch(17%_0.03_200)]"
            style={{ background: 'linear-gradient(180deg, oklch(72% 0.14 190), oklch(66% 0.13 184))' }}>
            <Bolt className="h-4 w-4" /> Başlat
          </button>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <Metric label="Frekans" value="0 Hz" tint="oklch(66% 0.13 184)" />
          <Metric label="Yoğunluk" value="0 mT" tint="oklch(78% 0.15 80)" />
          <Metric label="Süre" value="0 dk" tint="oklch(72% 0.17 152)" />
        </div>

        {/* Yama notları mini panel */}
        <div className="mt-3 rounded-lg border border-white/8 p-3" style={panel}>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-xs font-semibold text-white/70">Yama Notları · v{CLIENT.version}</span>
            <span className="text-[11px] text-white/35">{CLIENT.releaseDate}</span>
          </div>
          <div className="space-y-1.5">
            {[70, 52, 84].map((w, i) => (
              <div key={i} className="h-1.5 rounded-full bg-white/10" style={{ width: `${w}%` }} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
