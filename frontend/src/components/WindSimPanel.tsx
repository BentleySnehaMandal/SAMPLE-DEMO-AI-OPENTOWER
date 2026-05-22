import { useAppStore } from '../store/appStore';
import {
  XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, CartesianGrid, Legend, RadarChart, PolarGrid,
  PolarAngleAxis, PolarRadiusAxis, Radar,
} from 'recharts';

export default function WindSimPanel() {
  const windSim = useAppStore((s) => s.windSim);
  const windParams = useAppStore((s) => s.windSim.windParams);
  const setIntensity = useAppStore((s) => s.setWindIntensity);
  const setDirection = useAppStore((s) => s.setWindDirection);
  const toggle = useAppStore((s) => s.toggleWindOption);
  const sendWS = (data: object) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).__towerWSSend?.(data);
  };

  const handleIntensity = (v: number) => {
    setIntensity(v);
    sendWS({ type: 'wind_slider', intensity: v, direction: windSim.direction });
  };

  const handleDirection = (v: number) => {
    setDirection(v);
    sendWS({ type: 'wind_slider', intensity: windSim.intensity, direction: v });
  };

  if (!windSim.active || !windSim.result) {
    return (
      <div className="p-4 text-sm text-gray-500">
        <div className="text-center mt-4">
          <div className="text-2xl mb-2">🌬️</div>
          <div>Run wind analysis first.</div>
          <div className="text-xs mt-1">Try: "Run wind analysis at 50 m/s"</div>
        </div>
      </div>
    );
  }

  const { result } = windSim;
  const radarData = result.load_cases.map((lc) => ({
    direction: `${lc.direction}°`,
    deflection: lc.tip_deflection,
    stress: lc.max_stress_ratio,
  }));

  const pressureData = result.pressure_profile;

  return (
    <div className="p-3 space-y-4 overflow-y-auto h-full text-sm">
      {/* Summary */}
      <div className="grid grid-cols-2 gap-2">
        <StatCard label="Max Deflection" value={`${result.max_deflection_m.toFixed(3)} m`} color="text-red-400" />
        <StatCard label="Stability Index" value={result.stability_index.toFixed(3)} color={result.stability_index > 0.5 ? 'text-green-400' : 'text-amber-400'} />
        <StatCard label="Critical Dir" value={`${result.critical_direction}°`} color="text-blue-400" />
        <StatCard label="Load Cases" value={`${result.load_cases.length}`} color="text-gray-300" />
      </div>

      {/* Wind intensity slider */}
      <div>
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>Wind Intensity</span>
          <span>{(windSim.intensity * 100).toFixed(0)}%</span>
        </div>
        <input
          type="range" min={0} max={1} step={0.01}
          value={windSim.intensity}
          onChange={(e) => handleIntensity(parseFloat(e.target.value))}
          className="w-full accent-blue-500"
        />
      </div>

      {/* Direction slider */}
      <div>
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>Wind Direction</span>
          <span>{windSim.direction}°</span>
        </div>
        <input
          type="range" min={0} max={360} step={10}
          value={windSim.direction}
          onChange={(e) => handleDirection(parseInt(e.target.value))}
          className="w-full accent-cyan-500"
        />
      </div>

      {/* Toggles */}
      <div className="flex flex-wrap gap-2 text-xs">
        {([
          ['showOriginal', 'Original Tower'],
          ['showDeformed', 'Deformed Tower'],
          ['showWindArrows', 'Wind Arrows'],
        ] as const).map(([k, label]) => (
          <button
            key={k}
            onClick={() => toggle(k)}
            className={`px-2 py-1 rounded transition-colors ${
              windSim[k] ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Download report */}
      <button
        onClick={() => sendWS({ type: 'request_report' })}
        className="block w-full text-center text-xs bg-green-700 hover:bg-green-600 text-white rounded py-2 transition-colors"
      >
        📄 Download PDF Report
      </button>

      {/* Analysis parameters (wind speed, exposure, ice) */}
      {windParams && (
        <div>
          <div className="text-xs text-gray-400 uppercase tracking-wider mb-2">Analysis Parameters</div>
          <div className="bg-gray-800 rounded-lg p-3 space-y-1 text-xs">
            <ParamRow label="Wind Speed" value={`${windParams.service_wind_speed} m/s`} />
            <ParamRow label="Direction" value={`${windParams.direction_deg}°`} />
            <ParamRow label="Struct. Class" value={windParams.structural_class} />
            <ParamRow label="Exposure" value={windParams.exposure_category} />
            {windParams.ice_thickness > 0 && (
              <>
                <div className="border-t border-gray-700 pt-1 mt-1">
                  <span className="text-blue-300 font-medium">❄️ Ice Loading Active</span>
                </div>
                <ParamRow label="Ice Thickness" value={`${windParams.ice_thickness} mm`} />
                <ParamRow label="Ice Density" value={`${windParams.ice_density} kg/m³`} />
                <ParamRow label="Ice Wind Speed" value={`${windParams.ice_wind_speed} m/s`} />
              </>
            )}
          </div>
        </div>
      )}

      {/* Polar radar */}
      <div>
        <div className="text-xs text-gray-400 mb-1">12-Direction Analysis</div>
        <ResponsiveContainer width="100%" height={200}>
          <RadarChart data={radarData}>
            <PolarGrid stroke="#333" />
            <PolarAngleAxis dataKey="direction" tick={{ fontSize: 9, fill: '#888' }} />
            <PolarRadiusAxis tick={{ fontSize: 8, fill: '#666' }} />
            <Radar name="Deflection (m)" dataKey="deflection" stroke="#ff4444" fill="#ff4444" fillOpacity={0.3} />
            <Legend wrapperStyle={{ fontSize: 10 }} />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* Pressure profile */}
      <div>
        <div className="text-xs text-gray-400 mb-1">Wind Pressure vs Height</div>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={pressureData} layout="vertical">
            <CartesianGrid stroke="#333" strokeDasharray="3 3" />
            <XAxis type="number" dataKey="pressure" tick={{ fontSize: 9, fill: '#888' }} unit=" Pa" />
            <YAxis type="number" dataKey="height" tick={{ fontSize: 9, fill: '#888' }} unit=" m" />
            <Tooltip
              contentStyle={{ background: '#1a1a2e', border: '1px solid #444', fontSize: 11 }}
            />
            <Line type="monotone" dataKey="pressure" stroke="#00aaff" dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Load cases table */}
      <div>
        <div className="text-xs text-gray-400 mb-1">Load Cases</div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-gray-300">
            <thead>
              <tr className="border-b border-gray-700 text-gray-500">
                <th className="py-1 text-left">Dir°</th>
                <th className="py-1 text-right">Shear kN</th>
                <th className="py-1 text-right">Defl m</th>
                <th className="py-1 text-right">SR</th>
              </tr>
            </thead>
            <tbody>
              {result.load_cases.map((lc) => (
                <tr key={lc.direction} className="border-b border-gray-800 hover:bg-gray-800">
                  <td className="py-1">{lc.direction}°</td>
                  <td className="py-1 text-right">{lc.base_shear}</td>
                  <td className="py-1 text-right">{lc.tip_deflection}</td>
                  <td className={`py-1 text-right ${lc.max_stress_ratio > 0.7 ? 'text-red-400' : 'text-green-400'}`}>
                    {lc.max_stress_ratio}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="bg-gray-800 rounded-lg p-2">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-base font-bold font-mono ${color}`}>{value}</div>
    </div>
  );
}

function ParamRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-gray-400">{label}</span>
      <span className="text-gray-200 font-mono">{value}</span>
    </div>
  );
}
