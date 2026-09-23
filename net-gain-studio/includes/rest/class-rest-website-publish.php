<?php
/**
 * POST /net-gain/v1/episodes/{id}/publish-website - the WordPress-side half
 * of Section 6.2. Everything here runs inside the same WordPress process as
 * the audio file (unlike Captivate publishing, Section 6.1, which has to
 * round-trip the audio over HTTP) - no download/re-upload needed.
 *
 * Creates, lazily and idempotently: the show's "series" taxonomy term, the
 * top-level /shows/ hub page, the show's own /shows/{slug}/ hub page, and
 * the public `podcast` CPT post itself (Seriously Simple Podcasting's own
 * post type - confirmed via its source, see class-website-rewrite.php).
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_REST_Website_Publish {

	public function register_routes() {
		register_rest_route(
			'net-gain/v1',
			'/episodes/(?P<id>\d+)/publish-website',
			array(
				'methods'             => 'POST',
				'callback'            => array( $this, 'publish' ),
				'permission_callback' => function ( WP_REST_Request $request ) {
					return Net_Gain_REST_Permissions::can_manage_episode( (int) $request['id'] );
				},
			)
		);
	}

	public function publish( WP_REST_Request $request ) {
		$episode_id = (int) $request['id'];
		$episode    = get_post( $episode_id );
		if ( ! $episode || Net_Gain_CPT_Episode::POST_TYPE !== $episode->post_type ) {
			return new WP_Error( 'ng_episode_not_found', 'Episode not found.', array( 'status' => 404 ) );
		}

		$show = get_post( (int) $episode->post_parent );
		if ( ! $show ) {
			return new WP_Error( 'ng_show_not_found', 'Parent show not found.', array( 'status' => 404 ) );
		}

		try {
			$term_id        = $this->ensure_series_term( $show->post_name, $show->post_title );
			$parent_page_id = $this->ensure_shows_parent_page();
			$this->ensure_show_hub_page( (int) $show->ID, $show->post_name, $show->post_title, $parent_page_id );
			$post_id = $this->create_or_update_episode_post( $episode_id, $episode, $term_id );
		} catch ( Exception $e ) {
			return new WP_Error( 'ng_website_publish_failed', $e->getMessage(), array( 'status' => 500 ) );
		}

		$permalink = get_permalink( $post_id );
		update_post_meta( $episode_id, 'ng_website_post_id', $post_id );
		update_post_meta( $episode_id, 'ng_url_website', $permalink );

		return rest_ensure_response( array( 'post_id' => $post_id, 'permalink' => $permalink ) );
	}

	private function ensure_series_term( $show_slug, $show_name ) {
		$term = get_term_by( 'slug', $show_slug, 'series' );
		if ( $term ) {
			return $term->term_id;
		}
		if ( ! taxonomy_exists( 'series' ) ) {
			throw new Exception( 'The "series" taxonomy does not exist - is Seriously Simple Podcasting active?' );
		}
		$result = wp_insert_term( $show_name, 'series', array( 'slug' => $show_slug ) );
		if ( is_wp_error( $result ) ) {
			throw new Exception( 'Could not create the series term: ' . $result->get_error_message() );
		}
		return $result['term_id'];
	}

	private function ensure_shows_parent_page() {
		$existing = get_page_by_path( 'shows' );
		if ( $existing ) {
			return $existing->ID;
		}
		$page_id = wp_insert_post(
			array(
				'post_type'    => 'page',
				'post_status'  => 'publish',
				'post_title'   => 'Our Shows',
				'post_name'    => 'shows',
				'post_content' => '[net_gain_shows_hub]',
			),
			true
		);
		if ( is_wp_error( $page_id ) ) {
			throw new Exception( 'Could not create the Shows hub page: ' . $page_id->get_error_message() );
		}
		return $page_id;
	}

	private function ensure_show_hub_page( $show_id, $show_slug, $show_name, $parent_id ) {
		$existing = get_page_by_path( "shows/{$show_slug}" );
		if ( $existing ) {
			return $existing->ID;
		}
		$page_id = wp_insert_post(
			array(
				'post_type'    => 'page',
				'post_status'  => 'publish',
				'post_parent'  => $parent_id,
				'post_title'   => $show_name,
				'post_name'    => $show_slug,
				'post_content' => '[net_gain_show_episodes show_id="' . $show_id . '"]',
			),
			true
		);
		if ( is_wp_error( $page_id ) ) {
			throw new Exception( 'Could not create the show hub page: ' . $page_id->get_error_message() );
		}
		return $page_id;
	}

	private function create_or_update_episode_post( $episode_id, $episode, $term_id ) {
		$meta = array();
		foreach ( array( 'ng_script_final', 'ng_meta_aioseo_title', 'ng_meta_website_excerpt', 'ng_audio_attachment_id', 'ng_image_square_id', 'ng_talent_user_id', 'ng_website_post_id' ) as $key ) {
			$meta[ $key ] = get_post_meta( $episode_id, $key, true );
		}

		if ( empty( $meta['ng_audio_attachment_id'] ) ) {
			throw new Exception( 'No audio attached to this episode yet.' );
		}
		$audio_url = wp_get_attachment_url( $meta['ng_audio_attachment_id'] );

		// The script's own trailing "Show notes - story names and links" section
		// is split out into its own structured field (ng_story_links) rather than
		// left inline as bare URLs in the body (2026-09-20) - the design calls
		// for a distinct, labeled "Story Links" section, and bare long URLs with
		// no safe line-break points were also overflowing the mobile layout.
		$split = self::split_script( $meta['ng_script_final'] );
		update_post_meta( $episode_id, 'ng_story_links', $split['links'] );

		$postarr = array(
			'post_type'    => 'podcast',
			'post_status'  => 'publish',
			'post_title'   => $meta['ng_meta_aioseo_title'] ?: $episode->post_title,
			// linkify() is kept as a defensive pass over the narration body itself
			// (in case a story ever mentions a URL inline) even though the links
			// section above is no longer part of this string at all.
			'post_content' => self::linkify( wpautop( $split['body'] ) ),
			'post_excerpt' => $meta['ng_meta_website_excerpt'],
			'meta_input'   => array(
				'audio_file'            => $audio_url,
				'_ng_source_episode_id' => $episode_id,
			),
		);
		if ( $meta['ng_talent_user_id'] ) {
			$postarr['post_author'] = $meta['ng_talent_user_id'];
		}
		if ( $meta['ng_image_square_id'] ) {
			$postarr['meta_input']['cover_image_id'] = $meta['ng_image_square_id'];
		}

		if ( $meta['ng_website_post_id'] ) {
			$postarr['ID'] = $meta['ng_website_post_id'];
			$post_id       = wp_update_post( $postarr, true );
		} else {
			$post_id = wp_insert_post( $postarr, true );
		}
		if ( is_wp_error( $post_id ) ) {
			throw new Exception( 'Could not save the public episode post: ' . $post_id->get_error_message() );
		}

		wp_set_object_terms( $post_id, array( $term_id ), 'series' );

		return $post_id;
	}

	/**
	 * make_clickable() (WP core) turns bare URLs in the script's own "story
	 * names and links" section into real <a> tags - it adds no rel attribute
	 * of its own, so nofollow/noopener is injected after the fact. Safe as a
	 * blanket str_replace here specifically because the input at this point is
	 * AI-generated script text passed through wpautop()/make_clickable() -
	 * neither of those introduces an <a> tag any other way, so every
	 * `<a href=` in the string at this point is one make_clickable() just
	 * created from a bare URL.
	 */
	private static function linkify( $content ) {
		$content = make_clickable( $content );
		return str_replace( '<a href=', '<a rel="nofollow noopener" href=', $content );
	}

	/**
	 * Splits ng_script_final into the spoken narration (everything before the
	 * "Show notes" heading, matching every real script sampled so far - a
	 * trailing "---" divider then "**Show notes - story names and links:**")
	 * and a structured list of {title, url} pairs parsed from the numbered
	 * lines after it. Verified directly (2026-09-20) against 5 real episodes'
	 * ng_script_final, 18 links total, before being ported in here - both the
	 * quoted-title style ("Title" - url) and unquoted style (Title - url) the
	 * AI actually produces are handled. Titles are separated from their URL by
	 * an em dash specifically (not a hyphen), matching every real sample - a
	 * plain hyphen is deliberately not treated as a separator since titles
	 * themselves often contain one (e.g. "K-12").
	 *
	 * Returns array( 'body' => string, 'links' => array of [title, url] ).
	 * If no "Show notes" heading is found, 'body' is the whole script
	 * unchanged and 'links' is empty - fails soft, not loud, since this always
	 * runs as part of the wider publish flow and a missing links section
	 * shouldn't block the episode from publishing at all.
	 */
	private static function split_script( $script ) {
		$marker_pos = mb_strpos( $script, 'Show notes' );
		if ( false === $marker_pos ) {
			return array(
				'body'  => $script,
				'links' => array(),
			);
		}

		$body = mb_substr( $script, 0, $marker_pos );
		// Strip everything trailing between the real narration and the heading:
		// the "---" (or em/en-dash variant) divider line, AND the "**" bold-
		// markdown prefix immediately before "**Show notes...**" - both must be
		// handled in one pass, not two. A version that only stripped a bare
		// trailing "---" left "---\n\n**" as visible junk at the bottom of a
		// real published episode's body (confirmed live 2026-09-21) once a
		// script's divider was directly followed by the heading's own "**"
		// bold marker, since mb_strpos() finds "Show notes" itself, not the
		// "**" two characters before it, so that prefix stays in $body.
		$body = preg_replace( '/[\s\-*\x{2013}\x{2014}]+$/u', '', $body );
		$body = trim( $body );

		$links_section = mb_substr( $script, $marker_pos );
		// Drop the heading line itself ("Show notes - story names and links:" or similar).
		$links_section = preg_replace( '/^Show notes[^\n]*\n?/u', '', $links_section );

		preg_match_all(
			'/^\s*\d+\.\s*(.+?)\s*\x{2014}\s*(https?:\/\/\S+?)\s*$/mu',
			$links_section,
			$matches,
			PREG_SET_ORDER
		);

		$links = array();
		foreach ( $matches as $match ) {
			$title = preg_replace(
				'/^[\'"\x{2018}\x{2019}\x{201C}\x{201D}]+|[\'"\x{2018}\x{2019}\x{201C}\x{201D}]+$/u',
				'',
				trim( $match[1] )
			);
			$links[] = array(
				'title' => $title,
				'url'   => $match[2],
			);
		}

		return array(
			'body'  => $body,
			'links' => $links,
		);
	}
}
