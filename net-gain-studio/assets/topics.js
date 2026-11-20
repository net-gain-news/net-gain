/* Topics pages (templates/topics.php): search and sort on the list; narrowing on a topic's timeline.
   The pages are complete HTML without this script. Everything here only hides, shows and reorders what is already there. */
(function () {
	'use strict';
	document.documentElement.classList.add('ng-js');

	function each(list, fn) { Array.prototype.forEach.call(list, fn); }
	function key(li, mode) {
		if (mode === 'name') { return li.getAttribute('data-name') || ''; }
		return null;
	}
	function sortItems(ul, mode) {
		var items = Array.prototype.filter.call(ul.children, function (li) { return li.classList.contains('ng-tp-item'); });
		items.sort(function (a, b) {
			var an = a.getAttribute('data-name') || '', bn = b.getAttribute('data-name') || '';
			var ac = +a.getAttribute('data-count') || 0, bc = +b.getAttribute('data-count') || 0;
			if (mode === 'name') { return an < bn ? -1 : an > bn ? 1 : 0; }
			if (mode === 'recent') {
				var al = a.getAttribute('data-latest') || '', bl = b.getAttribute('data-latest') || '';
				if (al !== bl) { return al < bl ? 1 : -1; }
			}
			if (ac !== bc) { return bc - ac; }
			return an < bn ? -1 : an > bn ? 1 : 0;
		});
		items.forEach(function (li) { ul.appendChild(li); });
	}

	/* ---- the topics list ---- */
	var controls = document.querySelector('.ng-tp-controls');
	if (controls) {
		controls.hidden = false;
		var input = controls.querySelector('.ng-tp-q');
		var sortSelect = controls.querySelector('.ng-tp-sort');
		var status = controls.querySelector('.ng-tp-status');
		var sections = document.querySelectorAll('.ng-tp-section');
		var kind = 'all';
		var expanded = {};

		each(document.querySelectorAll('.ng-tp-showall'), function (btn) {
			btn.hidden = false;
			btn.addEventListener('click', function () {
				var sec = btn.closest('.ng-tp-section');
				var open = sec.classList.toggle('is-open');
				btn.textContent = open ? 'Show fewer' : 'Show all ' + sec.querySelectorAll('.ng-tp-list > .ng-tp-item').length;
			});
		});

		each(document.querySelectorAll('.ng-tp-item'), function (li) {
			var kids = li.querySelector(':scope > .ng-tp-children');
			if (!kids) { return; }
			var count = kids.children.length;
			var btn = document.createElement('button');
			btn.type = 'button';
			btn.className = 'mono ng-tp-expand';
			btn.textContent = '+ ' + count + (count === 1 ? ' place' : ' places');
			btn.addEventListener('click', function () {
				var open = li.classList.toggle('is-expanded');
				btn.textContent = open ? '− ' + count + (count === 1 ? ' place' : ' places') : '+ ' + count + (count === 1 ? ' place' : ' places');
			});
			li.insertBefore(btn, kids);
		});

		function apply() {
			var term = input.value.trim().toLowerCase();
			var total = 0;
			each(sections, function (sec) {
				var inKind = kind === 'all' || sec.getAttribute('data-kind') === kind;
				var visible = 0;
				each(sec.querySelectorAll('.ng-tp-list > .ng-tp-item'), function (li) {
					var own = !term || (li.getAttribute('data-name') || '').indexOf(term) > -1;
					var kidMatch = false;
					each(li.querySelectorAll(':scope > .ng-tp-children > .ng-tp-item'), function (kid) {
						var m = !term || own || (kid.getAttribute('data-name') || '').indexOf(term) > -1;
						kid.classList.toggle('is-hidden', !m);
						if (m && term && !own) { kidMatch = true; }
					});
					var show = own || kidMatch;
					li.classList.toggle('is-hidden', !show);
					if (term && li.querySelector(':scope > .ng-tp-children')) { li.classList.add('is-expanded'); }
					if (show) { visible++; }
				});
				sec.classList.toggle('is-searching', !!term);
				sec.hidden = !inKind || visible === 0;
				if (inKind) { total += visible; }
			});
			status.textContent = term || kind !== 'all' ? total + (total === 1 ? ' match' : ' matches') : '';
		}

		input.addEventListener('input', apply);
		sortSelect.addEventListener('change', function () {
			each(document.querySelectorAll('.ng-tp-list, .ng-tp-children'), function (ul) { sortItems(ul, sortSelect.value); });
		});
	}

	/* ---- a topic's timeline ---- */
	var refine = document.querySelector('.ng-refine');
	if (refine) {
		refine.hidden = false;
		var months = document.querySelectorAll('.ng-month');
		var shown = document.querySelector('.ng-tp-shown');
		var total = shown ? +shown.getAttribute('data-total') : 0;
		var initial = Array.prototype.map.call(months, function (m) { return m.open; });
		var buttons = refine.querySelectorAll('.ng-filter');

		each(buttons, function (btn) {
			btn.addEventListener('click', function () {
				var tag = btn.getAttribute('data-tag');
				each(buttons, function (b) { b.classList.toggle('is-on', b === btn); });
				var count = 0;
				each(months, function (month, i) {
					var here = 0;
					each(month.querySelectorAll('.ng-timeline > li'), function (li) {
						var tags = ' ' + (li.getAttribute('data-tags') || '') + ' ';
						var ok = !tag || tags.indexOf(' ' + tag + ' ') > -1;
						li.classList.toggle('is-hidden', !ok);
						if (ok) { here++; }
					});
					count += here;
					month.hidden = here === 0;
					var label = month.querySelector('.ng-month-count');
					if (label) { label.textContent = here + (here === 1 ? ' newscast' : ' newscasts'); }
					month.open = tag ? here > 0 : initial[i];
				});
				if (shown) { shown.textContent = tag ? count + ' of ' + total + ' newscasts' : total + (total === 1 ? ' newscast' : ' newscasts'); }
			});
		});
	}
})();
