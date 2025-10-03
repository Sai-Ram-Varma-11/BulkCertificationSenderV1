(function(){
	const $$ = (s,ctx=document)=>Array.from(ctx.querySelectorAll(s));
	const $ = (s,ctx=document)=>ctx.querySelector(s);

	const chkAll = $('#chkAll');
	const rowChks = $$('.rowchk');
	const genForm = $('#generateForm');
	const sendForm = $('#sendForm');
	const selectedCount = $('#selectedCount');
	const tableForms = $('#tableForms');
	const csvInput = $('#csvInput');
	const csvName = $('#csvName');

	function updateSelection(){
		const ids = rowChks.filter(c=>c.checked).map(c=>c.value);
		selectedCount && (selectedCount.textContent = ids.length + ' selected');
		// clear old hidden inputs
		$$('input[name="participant_id"][type="hidden"]', genForm).forEach(e=>e.remove());
		$$('input[name="participant_id"][type="hidden"]', sendForm).forEach(e=>e.remove());
		ids.forEach(id=>{
			const a = document.createElement('input'); a.type='hidden'; a.name='participant_id'; a.value=id; genForm.appendChild(a);
			const b = document.createElement('input'); b.type='hidden'; b.name='participant_id'; b.value=id; sendForm.appendChild(b);
		});
	}

	if(chkAll){
		chkAll.addEventListener('change',()=>{rowChks.forEach(c=>c.checked=chkAll.checked); updateSelection();});
	}
	rowChks.forEach(c=>c.addEventListener('change',updateSelection));
	updateSelection();

	if(csvInput && csvName){
		csvInput.addEventListener('change',()=>{
			csvName.textContent = csvInput.files && csvInput.files[0] ? csvInput.files[0].name : 'No file chosen';
		});
	}
})();
