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
		foreach ( array( 'ng_script_final', 'ng_meta_aioseo_title', 'ng_meta_website_excerpt', 'ng_meta_captivate_notes', 'ng_audio_attachment_id', 'ng_image_square_id', 'ng_talent_user_id', 'ng_website_post_id' ) as $key ) {
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

		// Episode-page-UX handoff (2026-09-23): promote Captivate-style show
		// notes above the transcript, with its own trailing "Stories & links"
		// paragraph stripped first - that would otherwise duplicate every link
		// already shown above via ng_story_links (a real one, not a hypothetical:
		// confirmed directly against a real published episode's ng_meta_captivate_notes).
		update_post_meta( $episode_id, 'ng_website_show_notes', self::website_show_notes( $meta['ng_meta_captivate_notes'] ) );

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
	 * Splits ng_script_final into the spoken narration and a structured list
	 * of {title, url} pairs parsed from a trailing numbered links section.
	 *
	 * Locates that section by finding the FIRST line matching the numbered
	 * link pattern itself ("N. "Title" — url"), not by searching for a
	 * "Show notes" heading - pipeline/script_generation.py's own prompt
	 * never actually instructs a heading at all (confirmed directly,
	 * 2026-09-23: no "show notes" / "links" / "source" instruction anywhere
	 * in that file), so the heading some scripts show is the AI's own
	 * unprompted, inconsistent convention, not a documented contract. A
	 * live episode confirmed this the hard way the same day: its script
	 * jumped straight from the sign-off line into "1. ... — url" with no
	 * heading, no "---" divider, and no "Show notes" text anywhere in the
	 * script - the old heading-text search found nothing, so that entire
	 * links section leaked into the published body as bare, unlinked text
	 * and ng_story_links came back empty. Searching for the links'
	 * *shape*, not a heading's wording, is robust to any convention (or
	 * none) the AI settles on.
	 *
	 * Verified directly (2026-09-20, re-verified 2026-09-23 against a wider
	 * sample including the no-heading case above) - both the quoted-title
	 * style ("Title" - url) and unquoted style (Title - url) the AI
	 * produces are handled. Titles are separated from their URL by an em
	 * dash specifically (not a hyphen), matching every real sample - a
	 * plain hyphen is deliberately not treated as a separator since titles
	 * themselves often contain one (e.g. "K-12").
	 *
	 * Returns array( 'body' => string, 'links' => array of [title, url] ).
	 * If no numbered link line is found at all, 'body' is the whole script
	 * unchanged and 'links' is empty - fails soft, not loud, since this
	 * always runs as part of the wider publish flow and a missing links
	 * section shouldn't block the episode from publishing at all.
	 */
	private static function split_script( $script ) {
		$link_line_pattern = '/^\s*\d+\.\s*.+?\s*\x{2014}\s*https?:\/\/\S+?\s*$/mu';

		$found = preg_match( $link_line_pattern, $script, $first_link_match );
		if ( ! $found ) {
			return array(
				'body'  => $script,
				'links' => array(),
			);
		}

		// mb_strpos() on the matched STRING, not preg_match's own byte offset
		// (PREG_OFFSET_CAPTURE) - this script contains multibyte characters
		// (em dashes, curly quotes), and preg's byte offsets don't line up
		// with mb_substr()'s character offsets, which would risk splitting a
		// multibyte character mid-sequence.
		$marker_pos = mb_strpos( $script, $first_link_match[0] );

		$body = mb_substr( $script, 0, $marker_pos );
		// Strip a trailing heading line naming the links section, in
		// whatever phrasing/wrapping the AI used this time - with or
		// without a "---" divider before it, with or without ** bold
		// markers, or (see above) no heading at all, in which case this
		// simply matches nothing and the next line handles the bare
		// divider/whitespace that's left.
		$body = preg_replace( '/\**\s*(?:show notes|stories\s*(?:&(?:amp;)?)?\s*(?:names\s*(?:and|&)\s*)?links)[^\n]*:?\**\s*$/iu', '', $body );
		// Strip whatever divider/whitespace debris is left right before the
		// heading (or right before the links themselves, if there was no
		// heading at all) - a "---" (or em/en-dash variant) divider line
		// and/or a stray "**" bold-markdown prefix.
		$body = preg_replace( '/[\s\-*\x{2013}\x{2014}]+$/u', '', $body );
		$body = trim( $body );

		$links_section = mb_substr( $script, $marker_pos );

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

	/**
	 * Strips Captivate notes' own trailing "Stories & links" section so the
	 * website's already-structured ng_story_links section (split_script(),
	 * above) isn't duplicated inline as prose too. Handles two real formats,
	 * not one assumed format - confirmed directly (2026-09-23) by actually
	 * publishing all 5 live episodes through this code, not just the newest:
	 *
	 * - Current (metadata_generation.py's prompt, 2026-09-14 onward): real
	 *   HTML, one <p> per story, ending in the exact literal marker
	 *   '<p><strong>Stories &amp; links:</strong></p>'.
	 * - Legacy (episode 44 only, predating that prompt's own <p>-tag fix -
	 *   its docblock explains why the fix exists: "after a live episode's
	 *   notes came back as one unbroken paragraph"): plain text, blank-line
	 *   paragraphs, no HTML at all, ending in ng_script_final's own
	 *   "**Show notes - story names and links:**" marker instead - captured
	 *   directly from the episode's raw ng_meta_captivate_notes, not
	 *   inferred. Detected by the absence of any '<p' tag, not an episode-
	 *   date cutoff, so this keeps working even if the true cutoff date
	 *   turns out to be approximate.
	 *
	 * Either way, a missing/no-match marker returns the input essentially
	 * unchanged (HTML) or wpautop()'d (legacy) - fails soft, matching
	 * split_script()'s own precedent, since the prompt itself documents an
	 * absent links section as a normal, valid state ("If the script has no
	 * such section, omit it rather than inventing one").
	 */
	private static function website_show_notes( $captivate_notes ) {
		if ( empty( $captivate_notes ) ) {
			return '';
		}

		$html_marker = '<p><strong>Stories &amp; links:</strong></p>';
		$marker_pos  = mb_strpos( $captivate_notes, $html_marker );
		if ( false !== $marker_pos ) {
			return trim( mb_substr( $captivate_notes, 0, $marker_pos ) );
		}

		if ( false === mb_strpos( $captivate_notes, '<p' ) ) {
			$legacy_marker_pos = mb_strpos( $captivate_notes, 'Show notes' );
			$body = false !== $legacy_marker_pos
				? mb_substr( $captivate_notes, 0, $legacy_marker_pos )
				: $captivate_notes;
			$body = preg_replace( '/[\s\-*\x{2013}\x{2014}]+$/u', '', $body );
			return wpautop( trim( $body ) );
		}

		return $captivate_notes;
	}
}
