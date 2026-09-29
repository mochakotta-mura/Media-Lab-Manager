(async function () {
  await window.mlmSessionReady;
  const user = await mlmSession.requireAdmin();
  const standard = document.querySelector('#standardLoanHours');
  const reminder = document.querySelector('#returnReminderHours');
  const notifyStaff = document.querySelector('#notifyStaff');
  const notifyStudents = document.querySelector('#notifyStudents');
  try {
    const settings = await mlmApi.settings();
    const read = value => { try { return JSON.parse(value); } catch { return value; } };
    if (settings.standardLoanHours) standard.value = String(read(settings.standardLoanHours));
    if (settings.returnReminderHours) reminder.value = String(read(settings.returnReminderHours));
    if (typeof settings.notifyStaff !== 'undefined') notifyStaff.checked = Boolean(read(settings.notifyStaff));
    if (typeof settings.notifyStudents !== 'undefined') notifyStudents.checked = Boolean(read(settings.notifyStudents));
    [['labHours', 'labHours'], ['pickupWindow', 'pickupWindow'], ['academicYear', 'academicYear']].forEach(([key, field]) => {
      if (settings[field]) document.querySelector(`[data-setting="${key}"]`).textContent = read(settings[field]);
    });
  } catch (error) { mlmUiError(error.message); }
  document.querySelector('#saveSettings').onclick = async () => {
    try {
      await mlmApi.updateSettings({ standardLoanHours: Number(standard.value), returnReminderHours: Number(reminder.value), notifyStaff: notifyStaff.checked, notifyStudents: notifyStudents.checked, actorId: user.id });
      const toast = document.querySelector('#toast'); toast.textContent = 'Settings saved'; toast.classList.add('show'); setTimeout(() => toast.classList.remove('show'), 2200);
    }
    catch (error) { mlmUiError(error.message); }
  };
})();
