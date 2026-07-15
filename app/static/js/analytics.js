// Analytics charts (Chart.js): stacked daily attendance + confidence trend.
(function () {
  const rangeSelect = document.getElementById('range-select');
  let attendanceChart = null;
  let confidenceChart = null;

  async function load(days) {
    const res = await fetch(`/api/analytics/${days}`);
    if (!res.ok) return;
    const data = await res.json();
    const labels = data.map((d) => d.date.slice(5)); // MM-DD

    attendanceChart?.destroy();
    attendanceChart = new Chart(document.getElementById('attendance-chart'), {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'Present', data: data.map((d) => d.present), backgroundColor: '#198754' },
          { label: 'Late', data: data.map((d) => d.late), backgroundColor: '#ffc107' },
          { label: 'Absent', data: data.map((d) => d.absent), backgroundColor: '#dc3545' },
        ],
      },
      options: {
        responsive: true,
        scales: {
          x: { stacked: true },
          y: { stacked: true, ticks: { precision: 0 } },
        },
      },
    });

    confidenceChart?.destroy();
    confidenceChart = new Chart(document.getElementById('confidence-chart'), {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Avg confidence',
          data: data.map((d) => d.avg_confidence),
          borderColor: '#0d6efd',
          tension: 0.3,
          spanGaps: true,
        }],
      },
      options: {
        responsive: true,
        scales: { y: { min: 0, max: 1 } },
      },
    });
  }

  rangeSelect.addEventListener('change', () => load(rangeSelect.value));
  load(rangeSelect.value);
})();
