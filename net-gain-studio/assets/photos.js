/* Net Gain Studio - Photos screen (drag-and-drop uploader, library grid, tag editor, runway meter).
   Plain JavaScript, no build step. Talks only to the net-gain/v1 photo routes (class-rest-photos.php). */
( function () {
	'use strict';

	var root = document.getElementById( 'ng-photos' );
	if ( ! root || ! window.ngPhotos ) { return; }

	var cfg = window.ngPhotos;
	var showId = parseInt( root.getAttribute( 'data-show' ), 10 );
	var state = { photos: [], filter: 'all', search: '', cooldown: 90, storage: { ok: true, outside_webroot: true }, stats: null };
	var pollTimer = null;

	var $ = function ( id ) { return document.getElementById( id ); };
	var TOPIC_LABELS = { higher_ed: 'higher ed', k12: 'K-12' };

	function el( tag, attrs, children ) {
		var node = document.createElement( tag );
		Object.keys( attrs || {} ).forEach( function ( key ) {
			if ( key === 'text' ) { node.textContent = attrs[ key ]; }
			else if ( key === 'class' ) { node.className = attrs[ key ]; }
			else if ( key.indexOf( 'on' ) === 0 ) { node.addEventListener( key.slice( 2 ), attrs[ key ] ); }
			else { node.setAttribute( key, attrs[ key ] ); }
		} );
		( children || [] ).forEach( function ( child ) {
			if ( child ) { node.appendChild( typeof child === 'string' ? document.createTextNode( child ) : child ); }
		} );
		return node;
	}

	function api( path, options ) {
		options = options || {};
		var headers = { 'X-WP-Nonce': cfg.nonce };
		if ( options.json ) { headers[ 'Content-Type' ] = 'application/json'; }
		return fetch( cfg.restUrl + path, {
			method: options.method || 'GET',
			headers: headers,
			credentials: 'same-origin',
			body: options.json ? JSON.stringify( options.json ) : undefined
		} ).then( function ( response ) {
			return response.json().then( function ( data ) {
				if ( ! response.ok ) { throw new Error( ( data && data.message ) || 'Request failed' ); }
				return data;
			} );
		} );
	}

	function thumbUrl( photo ) { return photo.thumb_url + ( photo.thumb_url.indexOf( '?' ) > -1 ? '&' : '?' ) + '_wpnonce=' + encodeURIComponent( cfg.nonce ); }
	function topicLabel( topic ) { return TOPIC_LABELS[ topic ] || topic; }

	// ---- data ------------------------------------------------------------------------------------

	function load() {
		return Promise.all( [ api( '/shows/' + showId + '/photos' ), api( '/shows/' + showId + '/photo-stats' ) ] ).then( function ( results ) {
			state.photos = results[ 0 ].photos;
			state.cooldown = results[ 0 ].cooldown_days;
			state.storage = results[ 0 ].storage;
			state.stats = results[ 1 ];
			render();
			schedulePoll();
		} ).catch( function ( error ) {
			$( 'ng-photos-meter' ).textContent = 'Could not load the library: ' + error.message;
		} );
	}

	function schedulePoll() {
		clearTimeout( pollTimer );
		var pending = state.photos.some( function ( p ) { return p.status === 'pending_tags'; } );
		if ( pending ) { pollTimer = setTimeout( load, 20000 ); }
	}

	// ---- rendering -------------------------------------------------------------------------------

	function render() {
		renderMeter();
		renderFilters();
		renderGrid();
	}

	function renderMeter() {
		var meter = $( 'ng-photos-meter' );
		var stats = state.stats;
		meter.className = 'ng-photos-meter';
		meter.textContent = '';
		if ( ! stats ) { return; }
		meter.classList.add( 'is-' + stats.level );

		var headline = {
			ok: 'Library healthy',
			low: 'Running low: add photos soon',
			urgent: 'Add photos now'
		}[ stats.level ];

		var numbers = el( 'div', { 'class': 'ng-photos-numbers' }, [
			stat( stats.eligible_now, 'ready to use' ),
			stat( stats.cooling_down, 'resting (' + stats.cooldown_days + '-day cooldown)' ),
			stat( stats.never_used, 'never used' ),
			stat( stats.eligible_no_faces, 'usable for sensitive stories' ),
			stat( stats.retired, 'retired' )
		] );

		var list = el( 'ul', {}, stats.messages.map( function ( m ) { return el( 'li', { text: m } ); } ) );
		meter.appendChild( el( 'strong', { text: headline } ) );
		meter.appendChild( numbers );
		meter.appendChild( list );
		if ( ! state.storage.ok ) {
			meter.appendChild( el( 'p', { 'class': 'ng-photos-warn', text: 'No private storage folder is writable - uploads will fail until your host allows it.' } ) );
		} else if ( ! state.storage.outside_webroot ) {
			meter.appendChild( el( 'p', { 'class': 'ng-photos-warn', text: 'Originals are stored in a protected folder inside the website, not outside it. Ask your host to allow a folder outside the web root for stronger protection.' } ) );
		}
	}

	function stat( value, label ) {
		return el( 'span', { 'class': 'ng-photos-stat' }, [ el( 'b', { text: String( value ) } ), ' ' + label ] );
	}

	var FILTERS = [
		[ 'all', 'All' ], [ 'fresh', 'Ready' ], [ 'cooling', 'Resting' ], [ 'pending', 'Tagging' ], [ 'nofaces', 'No identifiable people' ], [ 'retired', 'Retired' ]
	];

	function renderFilters() {
		var box = $( 'ng-photos-filters' );
		box.textContent = '';
		FILTERS.forEach( function ( f ) {
			var count = state.photos.filter( function ( p ) { return matches( p, f[ 0 ] ); } ).length;
			box.appendChild( el( 'button', {
				type: 'button',
				'class': 'button ' + ( state.filter === f[ 0 ] ? 'button-primary is-active' : '' ),
				text: f[ 1 ] + ' (' + count + ')',
				onclick: function () { state.filter = f[ 0 ]; render(); }
			} ) );
			box.appendChild( document.createTextNode( ' ' ) );
		} );
	}

	function matches( photo, filter ) {
		switch ( filter ) {
			case 'fresh': return photo.status === 'ready' && photo.eligible;
			case 'cooling': return photo.status === 'ready' && ! photo.eligible;
			case 'pending': return photo.status === 'pending_tags';
			case 'retired': return photo.status === 'retired';
			case 'nofaces': return photo.status === 'ready' && photo.people !== 'identifiable';
			default: return true;
		}
	}

	function visible() {
		var q = state.search.trim().toLowerCase();
		return state.photos.filter( function ( p ) {
			if ( ! matches( p, state.filter ) ) { return false; }
			if ( ! q ) { return true; }
			return ( p.tags.join( ' ' ) + ' ' + p.description + ' ' + p.name + ' ' + p.topics.join( ' ' ) ).toLowerCase().indexOf( q ) > -1;
		} );
	}

	function badge( text, cls ) { return el( 'span', { 'class': 'ng-photo-badge ' + ( cls || '' ), text: text } ); }

	function renderGrid() {
		var grid = $( 'ng-photos-grid' );
		grid.textContent = '';
		var list = visible();
		if ( ! list.length ) {
			grid.appendChild( el( 'p', { 'class': 'description', text: state.photos.length ? 'No photos match this filter.' : 'No photos yet. Drop some above to get started.' } ) );
			return;
		}
		list.forEach( function ( photo ) {
			var status;
			if ( photo.status === 'pending_tags' ) { status = badge( 'Tagging...', 'is-pending' ); }
			else if ( photo.status === 'retired' ) { status = badge( 'Retired', 'is-retired' ); }
			else if ( photo.eligible ) { status = badge( photo.use_count ? 'Ready' : 'Fresh', 'is-ready' ); }
			else { status = badge( 'Resting until ' + photo.available_on, 'is-cooling' ); }

			var people = photo.people ? badge( photo.people === 'identifiable' ? 'people visible' : ( photo.people === 'anonymous' ? 'people, no faces' : 'no people' ), photo.people === 'identifiable' ? 'is-faces' : '' ) : null;
			var low = photo.flags.indexOf( 'low_res' ) > -1 ? badge( 'low resolution', 'is-warn' ) : null;

			grid.appendChild( el( 'button', { type: 'button', 'class': 'ng-photo-card', onclick: function () { openModal( photo ); } }, [
				el( 'img', { src: thumbUrl( photo ), alt: photo.description || photo.name, loading: 'lazy' } ),
				el( 'span', { 'class': 'ng-photo-meta' }, [
					status, people, low,
					el( 'span', { 'class': 'ng-photo-tags', text: photo.tags.slice( 0, 4 ).join( ', ' ) } ),
					photo.use_count ? el( 'span', { 'class': 'ng-photo-used', text: 'used ' + photo.use_count + 'x' + ( photo.last_used ? ', last ' + photo.last_used : '' ) } ) : null
				] )
			] ) );
		} );
	}

	// ---- editor modal ------------------------------------------------------------------------------

	function openModal( photo ) {
		var modal = $( 'ng-photos-modal' );
		modal.textContent = '';
		modal.hidden = false;

		var focal = { x: photo.focal_x, y: photo.focal_y };
		var img = el( 'img', { src: thumbUrl( photo ), alt: '' } );
		var marker = el( 'span', { 'class': 'ng-focal' } );
		function placeMarker() { marker.style.left = ( focal.x * 100 ) + '%'; marker.style.top = ( focal.y * 100 ) + '%'; }
		placeMarker();
		var stage = el( 'div', { 'class': 'ng-focal-stage', title: 'Click to set the point that must stay in every crop' }, [ img, marker ] );
		stage.addEventListener( 'click', function ( event ) {
			var rect = img.getBoundingClientRect();
			focal.x = Math.max( 0, Math.min( 1, ( event.clientX - rect.left ) / rect.width ) );
			focal.y = Math.max( 0, Math.min( 1, ( event.clientY - rect.top ) / rect.height ) );
			placeMarker();
		} );

		var tags = el( 'input', { type: 'text', 'class': 'large-text', value: photo.tags.join( ', ' ) } );
		var description = el( 'textarea', { rows: '2', 'class': 'large-text' } );
		description.value = photo.description;
		var people = el( 'select', {}, cfg.people.map( function ( p ) {
			var opt = el( 'option', { value: p, text: { none: 'No people', anonymous: 'People, faces not identifiable', identifiable: 'People visible (identifiable)' }[ p ] } );
			if ( photo.people === p ) { opt.selected = true; }
			return opt;
		} ) );
		var topicBoxes = cfg.topics.map( function ( topic ) {
			var box = el( 'input', { type: 'checkbox', value: topic } );
			box.checked = photo.topics.indexOf( topic ) > -1;
			return el( 'label', { 'class': 'ng-topic' }, [ box, ' ' + topicLabel( topic ) ] );
		} );

		var message = el( 'p', { 'class': 'description' } );
		function saveFields( extra ) {
			var payload = {
				tags: tags.value.split( ',' ).map( function ( t ) { return t.trim(); } ).filter( Boolean ),
				description: description.value,
				people: people.value,
				topics: topicBoxes.map( function ( l ) { return l.firstChild; } ).filter( function ( b ) { return b.checked; } ).map( function ( b ) { return b.value; } ),
				focal_x: focal.x,
				focal_y: focal.y
			};
			Object.keys( extra || {} ).forEach( function ( key ) { payload[ key ] = extra[ key ]; } );
			message.textContent = 'Saving...';
			return api( '/photos/' + photo.id, { method: 'POST', json: payload } ).then( function () { closeModal(); return load(); } ).catch( function ( error ) { message.textContent = error.message; } );
		}

		var actions = [
			el( 'button', { type: 'button', 'class': 'button button-primary', text: 'Save', onclick: function () { saveFields(); } } ),
			photo.status === 'retired'
				? el( 'button', { type: 'button', 'class': 'button', text: 'Restore', onclick: function () { saveFields( { status: 'ready' } ); } } )
				: el( 'button', { type: 'button', 'class': 'button', text: 'Retire (stop using)', onclick: function () { saveFields( { status: 'retired' } ); } } ),
			el( 'button', { type: 'button', 'class': 'button', text: 'Tag again', title: 'Replaces these tags with a fresh automatic pass', onclick: function () {
				api( '/photos/' + photo.id, { method: 'POST', json: { status: 'pending_tags' } } ).then( function () { closeModal(); return load(); } );
			} } ),
			el( 'button', { type: 'button', 'class': 'button button-link-delete', text: 'Delete', onclick: function () {
				if ( window.confirm( 'Delete this photo permanently? Episodes that already used it keep their graphics.' ) ) {
					api( '/photos/' + photo.id, { method: 'DELETE' } ).then( function () { closeModal(); return load(); } );
				}
			} } ),
			el( 'button', { type: 'button', 'class': 'button', text: 'Close', onclick: closeModal } )
		];

		var used = photo.used_on && photo.used_on.length
			? el( 'p', { 'class': 'description', text: 'Used for episodes dated: ' + photo.used_on.map( function ( u ) { return u.date; } ).join( ', ' ) } )
			: el( 'p', { 'class': 'description', text: 'Not used yet.' } );

		modal.appendChild( el( 'div', { 'class': 'ng-photos-dialog', role: 'dialog', 'aria-modal': 'true' }, [
			el( 'div', { 'class': 'ng-photos-dialog-left' }, [ stage, el( 'p', { 'class': 'description', text: photo.name + ' - ' + photo.width + ' x ' + photo.height + ' px' } ) ] ),
			el( 'div', { 'class': 'ng-photos-dialog-right' }, [
				el( 'label', { text: 'Tags (comma separated)' } ), tags,
				el( 'label', { text: 'People in the photo' } ), people,
				el( 'label', { text: 'Suits stories about' } ), el( 'div', { 'class': 'ng-topics' }, topicBoxes ),
				el( 'label', { text: 'Description' } ), description,
				used, message,
				el( 'div', { 'class': 'ng-photos-actions' }, actions )
			] )
		] ) );
	}

	function closeModal() { var modal = $( 'ng-photos-modal' ); modal.hidden = true; modal.textContent = ''; }

	// ---- uploading -------------------------------------------------------------------------------

	var queue = [];
	var uploading = false;

	function addFiles( fileList ) {
		Array.prototype.forEach.call( fileList, function ( file ) {
			var row = el( 'div', { 'class': 'ng-upload-row' } );
			var label = el( 'span', { text: file.name } );
			var status = el( 'span', { 'class': 'ng-upload-status', text: 'waiting' } );
			var bar = el( 'progress', { max: '100', value: '0' } );
			row.appendChild( label ); row.appendChild( bar ); row.appendChild( status );
			$( 'ng-photos-uploads' ).appendChild( row );
			queue.push( { file: file, row: row, status: status, bar: bar } );
		} );
		pump();
	}

	function pump() {
		if ( uploading ) { return; }
		var job = queue.shift();
		if ( ! job ) { load(); return; }
		uploading = true;
		job.status.textContent = 'uploading';

		var form = new FormData();
		form.append( 'file', job.file );
		var xhr = new XMLHttpRequest();
		xhr.open( 'POST', cfg.restUrl + '/shows/' + showId + '/photos' );
		xhr.setRequestHeader( 'X-WP-Nonce', cfg.nonce );
		xhr.upload.addEventListener( 'progress', function ( event ) {
			if ( event.lengthComputable ) { job.bar.value = Math.round( event.loaded / event.total * 100 ); }
		} );
		xhr.onload = function () {
			var data = {};
			try { data = JSON.parse( xhr.responseText ); } catch ( e ) { /* not JSON */ }
			if ( xhr.status >= 200 && xhr.status < 300 ) {
				job.bar.value = 100;
				job.status.textContent = 'added - tagging will finish in a few minutes';
				job.row.classList.add( 'is-done' );
				setTimeout( function () { job.row.remove(); }, 6000 );
			} else {
				job.status.textContent = data.message || ( 'failed (' + xhr.status + ')' );
				job.row.classList.add( 'is-error' );
				job.row.appendChild( el( 'button', { type: 'button', 'class': 'button-link', text: 'dismiss', onclick: function () { job.row.remove(); } } ) );
			}
			uploading = false; pump();
		};
		xhr.onerror = function () {
			job.status.textContent = 'network error';
			job.row.classList.add( 'is-error' );
			uploading = false; pump();
		};
		xhr.send( form );
	}

	// ---- wiring ----------------------------------------------------------------------------------

	var drop = $( 'ng-photos-drop' );
	var input = $( 'ng-photos-input' );
	[ 'dragenter', 'dragover' ].forEach( function ( type ) {
		drop.addEventListener( type, function ( event ) { event.preventDefault(); drop.classList.add( 'is-over' ); } );
	} );
	[ 'dragleave', 'drop' ].forEach( function ( type ) {
		drop.addEventListener( type, function ( event ) { event.preventDefault(); drop.classList.remove( 'is-over' ); } );
	} );
	drop.addEventListener( 'drop', function ( event ) {
		if ( event.dataTransfer && event.dataTransfer.files.length ) { addFiles( event.dataTransfer.files ); }
	} );
	$( 'ng-photos-browse' ).addEventListener( 'click', function ( event ) { event.preventDefault(); input.click(); } );
	drop.addEventListener( 'keydown', function ( event ) { if ( event.key === 'Enter' || event.key === ' ' ) { event.preventDefault(); input.click(); } } );
	input.addEventListener( 'change', function () { if ( input.files.length ) { addFiles( input.files ); input.value = ''; } } );
	$( 'ng-photos-search' ).addEventListener( 'input', function ( event ) { state.search = event.target.value; renderGrid(); } );
	document.addEventListener( 'keydown', function ( event ) { if ( event.key === 'Escape' ) { closeModal(); } } );
	// Dropping a file anywhere else on the page must not make the browser navigate to it.
	[ 'dragover', 'drop' ].forEach( function ( type ) { window.addEventListener( type, function ( event ) { if ( ! drop.contains( event.target ) ) { event.preventDefault(); } } ); } );

	load();
}() );
