(async function () {
  await window.mlmSessionReady;
  const user = await mlmSession.requireAdmin();
  const selects = document.querySelectorAll('select');
  const checks = document.querySelectorAll('input[type="checkbox"]');
  try {
    const settings = await mlmApi.settings();
    if (settings.standardLoanHours) selects[0].value = String(JSON.parse(settings.standardLoanHours));
    if (settings.returnReminderHours) selects[1].value = String(JSON.parse(settings.returnReminderHours));
  } catch (error) { mlmUiError(error.message); }
  document.querySelector('#saveSettings').onclick = async () => {
    try { await mlmApi.updateSettings({ standardLoanHours: Number(selects[0].value), returnReminderHours: Number(selects[1].value), notifyStaff: checks[0]?.checked, notifyStudents: checks[1]?.checked, actorId: user.id }); alert('Settings saved.'); }
    catch (error) { mlmUiError(error.message); }
  };
})();
