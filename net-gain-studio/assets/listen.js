( function () {
	var top = document.getElementById( 'ngl-signup' );
	var bottom = document.getElementById( 'ngl-signup-bottom' );
	var bar = document.getElementById( 'ngl-bar' );
	var player = document.getElementById( 'ngl-player' );
	var engaged = false;   // the visitor has pressed play or scrolled past the episode: only then may the phone signup bar appear
	var onEngaged = function () {};
	if ( ! top ) return;

	function track( name, params ) {
		if ( typeof window.gtag === 'function' ) {
			params = params || {};
			params.method = 'edtech_invite';
			window.gtag( 'event', name, params );
		}
	}

	// Play: the Listen button and the play button on the episode picture both send Captivate's CP.API.PLAY to the player
	// (the same postMessage the episode pages use). Browsers decide per click whether a cross-origin frame may start audio,
	// so a second try follows if it is still paused, and if that fails too the player is outlined to show where to press.
	if ( player ) {
		var awaiting = false;
		var tries = 0;
		var send = function ( action ) {
			try { player.contentWindow.postMessage( { action: action }, '*' ); } catch ( e ) {}
		};
		window.addEventListener( 'message', function ( e ) {
			if ( ! awaiting || e.source !== player.contentWindow || ! e.data || e.data.event !== 'CP.API.CALLBACK.GET_PAUSED' ) return;
			awaiting = false;
			if ( true !== e.data.data ) return;
			if ( tries < 1 ) {
				tries++;
				send( 'CP.API.PLAY' );
				awaiting = true;
				setTimeout( function () { send( 'CP.API.GET_PAUSED' ); }, 700 );
			} else {
				var box = player.parentNode;
				box.style.outline = '3px solid #d0202c';
				setTimeout( function () { box.style.outline = ''; }, 2200 );
			}
		} );
		var play = function ( source ) {
			var r = player.getBoundingClientRect();
			if ( r.top < 0 || r.bottom > window.innerHeight ) {
				player.scrollIntoView( { behavior: 'smooth', block: 'center' } );
			}
			tries = 0;
			send( 'CP.API.PLAY' );
			awaiting = true;
			setTimeout( function () { send( 'CP.API.GET_PAUSED' ); }, 700 );
			track( 'listen_play', { control: source } );
			engaged = true;
			onEngaged();
		};
		document.querySelectorAll( '[data-ngl-play]' ).forEach( function ( el ) {
			var source = el.getAttribute( 'data-ngl-play' );
			el.addEventListener( 'click', function () { play( source ); } );
			if ( 'BUTTON' !== el.tagName ) {
				el.addEventListener( 'keydown', function ( e ) {
					if ( 'Enter' === e.key || ' ' === e.key ) {
						e.preventDefault();
						play( source );
					}
				} );
			}
		} );
	}

	function focusEmail() {
		var input = top.querySelector( 'input[type="email"]' );
		if ( input ) {
			try { input.focus( { preventScroll: true } ); } catch ( e ) { input.focus(); }
		}
	}

	// Count a signup in Google Analytics (Site Kit loads gtag); the visit's utm_ tags then say which email wave it came from.
	document.querySelectorAll( '.ngl-form' ).forEach( function ( form ) {
		form.addEventListener( 'submit', function () {
			track( 'generate_lead', { form_position: form.getAttribute( 'data-ngl-form' ) || '' } );
		} );
	} );

	if ( ! bar || ! ( 'IntersectionObserver' in window ) ) return;

	// The phone bar shows only after the visitor has had the chance to listen, and only while neither signup box (nor the footer) is on screen.
	var visible = {};
	function update() {
		var hide = ! engaged || visible.top || visible.bottom || visible.footer;
		bar.classList.toggle( 'is-on', ! hide );
		bar.setAttribute( 'aria-hidden', hide ? 'true' : 'false' );
		var btn = bar.querySelector( '.ngl-bar-btn' );
		if ( btn ) btn.tabIndex = hide ? -1 : 0;
	}
	var io = new IntersectionObserver( function ( entries ) {
		entries.forEach( function ( e ) {
			var key = e.target.getAttribute( 'data-ngl-watch' );
			if ( 'hero' === key ) {
				if ( ! e.isIntersecting && e.boundingClientRect.bottom < 0 ) engaged = true;   // scrolled past the episode
				return;
			}
			visible[ key ] = e.isIntersecting;
		} );
		update();
	} );
	onEngaged = update;
	[ [ top, 'top' ], [ bottom, 'bottom' ], [ document.querySelector( '.site-footer' ), 'footer' ], [ document.getElementById( 'ngl-hero' ), 'hero' ] ].forEach( function ( pair ) {
		if ( ! pair[ 0 ] ) return;
		pair[ 0 ].setAttribute( 'data-ngl-watch', pair[ 1 ] );
		io.observe( pair[ 0 ] );
	} );

	bar.querySelector( '.ngl-bar-btn' ).addEventListener( 'click', function () {
		top.scrollIntoView( { behavior: 'smooth', block: 'center' } );
		setTimeout( focusEmail, 450 );
	} );
} )();
