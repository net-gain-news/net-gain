( function () {
	var top = document.getElementById( 'ngl-signup' );
	var bottom = document.getElementById( 'ngl-signup-bottom' );
	var bar = document.getElementById( 'ngl-bar' );
	if ( ! top ) return;

	function focusEmail() {
		var input = top.querySelector( 'input[type="email"]' );
		if ( input ) {
			try { input.focus( { preventScroll: true } ); } catch ( e ) { input.focus(); }
		}
	}

	// Count a signup in Google Analytics (Site Kit loads gtag); the visit's utm_ tags then say which email wave it came from.
	document.querySelectorAll( '.ngl-form' ).forEach( function ( form ) {
		form.addEventListener( 'submit', function () {
			if ( typeof window.gtag === 'function' ) {
				window.gtag( 'event', 'generate_lead', { method: 'edtech_invite', form_position: form.getAttribute( 'data-ngl-form' ) || '' } );
			}
		} );
	} );

	if ( ! bar || ! ( 'IntersectionObserver' in window ) ) return;

	// The phone bar shows only while neither signup box (nor the footer) is on screen.
	var visible = {};
	function update() {
		var hide = visible.top || visible.bottom || visible.footer;
		bar.classList.toggle( 'is-on', ! hide );
		bar.setAttribute( 'aria-hidden', hide ? 'true' : 'false' );
		var btn = bar.querySelector( '.ngl-bar-btn' );
		if ( btn ) btn.tabIndex = hide ? -1 : 0;
	}
	var io = new IntersectionObserver( function ( entries ) {
		entries.forEach( function ( e ) { visible[ e.target.getAttribute( 'data-ngl-watch' ) ] = e.isIntersecting; } );
		update();
	} );
	[ [ top, 'top' ], [ bottom, 'bottom' ], [ document.querySelector( '.site-footer' ), 'footer' ] ].forEach( function ( pair ) {
		if ( ! pair[ 0 ] ) return;
		pair[ 0 ].setAttribute( 'data-ngl-watch', pair[ 1 ] );
		io.observe( pair[ 0 ] );
	} );

	bar.querySelector( '.ngl-bar-btn' ).addEventListener( 'click', function () {
		top.scrollIntoView( { behavior: 'smooth', block: 'center' } );
		setTimeout( focusEmail, 450 );
	} );
} )();
