import type { Locale } from '../../composables/i18n'
import { chatChromeMessages } from '../../locales/chatChromeMessages'
import { parseChartPayload } from './chartPayload'

export async function renderChartBlocks(
  locale: Locale,
  ensureScript: (url: string, globalName: string) => Promise<any>,
) {
  const canvases = Array.from(document.querySelectorAll('canvas.chart-block')) as HTMLCanvasElement[]
  if (!canvases.length) return
  const Chart = await ensureScript('https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js', 'Chart')
  if (!Chart) {
    console.error('[Chart] Failed to load Chart.js')
    return
  }
  for (const canvas of canvases) {
    if (canvas.dataset.rendered === 'true') continue
    const raw = canvas.dataset.chart || ''
    let payload: any
    try {
      const decoded = decodeURIComponent(raw)
      try {
        payload = JSON.parse(decoded)
      } catch {
        // Handle potentially escaped double quotes in malformed JSON
        const cleaned = decoded.replace(/\\"/g, '"')
        payload = JSON.parse(cleaned)
      }
    } catch (e) {
      const decoded = decodeURIComponent(raw)
      payload = parseChartPayload(decoded)
      if (!payload) {
        console.error('[Chart] Failed to parse chart data:', e)
        continue
      }
    }

    // Support multiple formats:
    // 1. Simplified: {type, labels/xAxis, series: [{name, data}]}
    // 2. Chart.js native: {type, data: {labels, datasets}, options}
    let type = (payload.type || 'line').toLowerCase()
    if (type === 'column') type = 'bar'
    if (type === 'sankey') {
      await ensureScript('https://cdn.jsdelivr.net/npm/chartjs-chart-sankey@0.13.0/dist/chartjs-chart-sankey.min.js', 'chartjsChartSankey')
      // Ensure sankey controller is registered with Chart.js (UMD bundles may not auto-register)
      const candidates = [
        (Chart as any),
        (window as any),
        (window as any).ChartSankey,
        (window as any).chartjsChartSankey,
        (window as any).ChartSankey?.default,
        (window as any).chartjsChartSankey?.default,
      ].filter(Boolean)
      let SankeyController: any
      let Flow: any
      for (const mod of candidates) {
        if (!SankeyController && (mod as any).SankeyController) {
          SankeyController = (mod as any).SankeyController
        }
        if (!Flow && (mod as any).Flow) {
          Flow = (mod as any).Flow
        }
      }
      if (SankeyController && Flow && (Chart as any).register) {
        try {
          ;(Chart as any).register(SankeyController, Flow)
        } catch (e) {
          console.warn('[Chart] Failed to register sankey controller:', e)
        }
      } else {
        console.warn('[Chart] Sankey controller not found after loading plugin')
      }
    }

    let labels: any[]
    let datasets: any[]
    let renderAsTable = false
    let tableRows: Array<[string, string]> = []

    const dataObj = payload.data || payload
    if (dataObj && dataObj.labels && dataObj.datasets) {
      // Chart.js native or semi-native format
      labels = dataObj.labels
      datasets = dataObj.datasets.map((ds: any) => ({
        ...ds,
        borderWidth: ds.borderWidth || 2,
        fill: ds.fill !== undefined ? ds.fill : (type === 'bar'),
      }))
    } else if (type === 'sankey' && payload.data && payload.data.links) {
      const links = payload.data.links || []
      const nodeNames = Array.isArray(payload.data.nodes)
        ? payload.data.nodes.map((n: any) => (n && n.name ? String(n.name) : String(n)))
        : []
      const derivedNames = new Set<string>()
      for (const link of links) {
        if (link.source !== undefined && link.source !== null) derivedNames.add(String(link.source))
        if (link.target !== undefined && link.target !== null) derivedNames.add(String(link.target))
      }
      const allNames = nodeNames.length ? nodeNames : Array.from(derivedNames)
      const nameSet = new Set(allNames)
      labels = allNames
      datasets = [{
        label: payload.title || 'Sankey',
        data: links
          .map((link: any) => ({
            from: String(link.source),
            to: String(link.target),
            flow: link.value ?? link.flow ?? 0
          }))
          .filter((link: any) => nameSet.has(link.from) && nameSet.has(link.to)),
        colorMode: 'gradient',
        colorFrom: '#7aa6ff',
        colorTo: '#7ecf9a',
        borderWidth: 1,
        borderColor: 'rgba(0,0,0,0.08)'
      }]
    } else if (payload.data && Array.isArray(payload.data) && payload.xField && payload.yField) {
      // Array of objects with xField + multiple yField
      const rows = payload.data
      const yFields = Array.isArray(payload.yField) ? payload.yField : [payload.yField]
      labels = rows.map((r: any) => r[payload.xField])
      datasets = yFields.map((field: string, idx: number) => ({
        label: field,
        data: rows.map((r: any) => r[field] ?? 0),
        borderWidth: 2,
        fill: type === 'bar',
      }))
    } else if (payload.data && payload.data.labels && payload.data.values) {
      // Simple format: {data:{labels, values}}
      labels = payload.data.labels
      datasets = [{
        label: payload.title || 'Series 1',
        data: payload.data.values,
        borderWidth: 2,
        fill: type === 'bar',
      }]
    } else if (payload.data && payload.data.values && Array.isArray(payload.data.values) && payload.type === 'pie') {
      // Pie format: {data:{values:[{category, value}]}}
      labels = payload.data.values.map((v: any) => v.category)
      datasets = [{
        label: payload.title || 'Series 1',
        data: payload.data.values.map((v: any) => v.value),
        borderWidth: 1,
      }]
      type = 'pie'
    } else if (payload.data && Array.isArray(payload.data) && type === 'bar' && !payload.xField) {
      // Array rows without explicit xField -> use first key as label, second as value
      const rows = payload.data
      const keys = rows.length ? Object.keys(rows[0]) : []
      const labelKey = keys[0]
      const valueKey = keys[1]
      const values = rows.map((r: any) => r[valueKey])
      const numeric = values.every((v: any) => typeof v === 'number' && !Number.isNaN(v))
      if (!numeric) {
        renderAsTable = true
        tableRows = rows.map((r: any) => [String(r[labelKey] ?? ''), String(r[valueKey] ?? '')])
        labels = []
        datasets = []
      } else {
        labels = rows.map((r: any) => r[labelKey])
        datasets = [{
          label: payload.title || valueKey || 'Series 1',
          data: values,
          borderWidth: 2,
          fill: true,
        }]
      }
    } else if (payload.series && payload.xAxis) {
      // ECharts-like format
      labels = payload.xAxis.data || payload.xAxis
      datasets = (payload.series || []).map((s: any, idx: number) => ({
        label: s.name || `Series ${idx + 1}`,
        data: s.data || [],
        borderWidth: 2,
        fill: type === 'bar',
      }))
    } else if (type === 'scatter' && payload.data && payload.data.datasets) {
      labels = []
      datasets = payload.data.datasets.map((ds: any) => ({
        ...ds,
        borderWidth: ds.borderWidth || 2,
      }))
    } else if (type === 'scatter' && payload.data && payload.xField && payload.yField) {
      // Scatter chart with xField/yField format
      labels = []
      const dataPoints = payload.data
      const seriesField = payload.seriesField

      if (seriesField) {
        // Group by series field
        const grouped = new Map<string, any[]>()
        for (const item of dataPoints) {
          const seriesName = item[seriesField]
          if (!grouped.has(seriesName)) {
            grouped.set(seriesName, [])
          }
          grouped.get(seriesName)!.push({
            x: item[payload.xField],
            y: item[payload.yField]
          })
        }

        datasets = Array.from(grouped.entries()).map(([name, data]) => ({
          label: name,
          data: data,
          borderWidth: 2,
        }))
      } else {
        // Single series
        datasets = [{
          label: payload.title || 'Data',
          data: dataPoints.map((item: any) => ({
            x: item[payload.xField],
            y: item[payload.yField]
          })),
          borderWidth: 2,
        }]
      }
    } else {
      // Simplified format (support labels, xAxis, or x)
      labels = payload.labels || payload.xAxis || payload.x || []
      const series = payload.series || []

      if (series.length === 0 && payload.y) {
        // Fallback for {x, y} format
        datasets = [{
          label: payload.yLabel || payload.title || 'Data',
          data: payload.y,
          borderWidth: 2,
          fill: type === 'bar',
        }]
      } else {
        datasets = series.map((s: any, idx: number) => ({
          label: s.name || `Series ${idx + 1}`,
          data: s.data || [],
          borderWidth: 2,
          fill: type === 'bar',
        }))
      }
    }

    const chartOptions = payload.options || { responsive: true, maintainAspectRatio: false }
    if (type === 'sankey') {
      chartOptions.parsing = { from: 'from', to: 'to', flow: 'flow' }
      chartOptions.plugins = chartOptions.plugins || {}
      chartOptions.plugins.legend = { display: false }
      chartOptions.plugins.tooltip = { enabled: true }
    }

    try {
      if (renderAsTable) {
        const container = canvas.parentElement
        if (container) {
          const header1 = payload.xField || chatChromeMessages.chartItem[locale]
          const header2 = payload.yField || chatChromeMessages.chartContent[locale]
          const table = document.createElement('table')
          table.className = 'w-full text-sm border border-gray-300 border-collapse'
          const thead = table.createTHead()
          const headerRow = thead.insertRow()
          for (const value of [header1, header2]) {
            const cell = document.createElement('th')
            cell.className = 'border border-gray-300 px-3 py-2 text-left'
            cell.textContent = String(value)
            headerRow.append(cell)
          }
          const body = table.createTBody()
          for (const [left, right] of tableRows) {
            const row = body.insertRow()
            for (const value of [left, right]) {
              const cell = row.insertCell()
              cell.className = 'border border-gray-300 px-3 py-2'
              cell.textContent = String(value)
            }
          }
          container.replaceChildren(table)
        }
        canvas.dataset.rendered = 'true'
        continue
      }
      const resolvedType = type === 'bar' || type === 'line' || type === 'pie' || type === 'scatter' || type === 'sankey'
        ? type
        : 'line'
      new (Chart as any)(canvas, {
        type: resolvedType,
        data: { labels, datasets },
        options: chartOptions,
      })
      canvas.dataset.rendered = 'true'
    } catch (e) {
      console.error('[Chart] Failed to render chart:', e)
    }
  }
}
