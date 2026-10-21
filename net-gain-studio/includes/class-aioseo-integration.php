<?php
/**
 * AIOSEO integration via its real hooks (Spec Section 6.2) - never its own
 * UI, never its own AI title/description generator. Confirmed against
 * AIOSEO's own documentation before writing this:
 *
 * - aioseo_description: a simple per-render filter, string -> string, no
 *   post-identifying parameter - fires in the context of whatever post is
 *   currently being rendered.
 * - There is no aioseo_title filter (checked against AIOSEO's complete,
 *   documented filter-hook list). The SEO title instead has to go through
 *   aioseo_save_post, which the spec calls an "action" but AIOSEO's own docs
 *   call a FILTER: it hands you AIOSEO's internal Post model and expects it
 *   returned, modified. AIOSEO's own docs say that model's property names
 *   are "subject to change" and recommend live inspection - $post->title
 *   below is the most likely name, not a confirmed one; see
 *   PHASE_6_HANDOFF.md for how to confirm it on first real use.
 *
 * No focus keyphrase field is set anywhere here - explicitly rejected by
 * the spec (Section 6.2).
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_AIOSEO_Integration {

	public static function register() {
		add_filter( 'aioseo_description', array( __CLASS__, 'filter_description' ) );
		add_filter( 'aioseo_save_post', array( __CLASS__, 'filter_save_post' ), 10, 2 );
		add_filter( 'aioseo_facebook_tags', array( __CLASS__, 'filter_facebook_tags' ) );
		add_filter( 'aioseo_twitter_tags', array( __CLASS__, 'filter_twitter_tags' ) );
	}

	/**
	 * The episode's own 1200x630 art as the Open Graph / Twitter share image
	 * (2026-10-06). AIOSEO would otherwise look for a featured image, and the
	 * public podcast post has none - the art hangs off the internal ng_episode
	 * post (ng_image_1200x630_id), the same one the theme shows on the page.
	 * Returns array( url, width, height ) or null when this is not an episode
	 * page or it has no art yet (AIOSEO's own fallback then applies).
	 */
	private static function share_image() {
		if ( ! is_singular( 'podcast' ) ) {
			return null;
		}
		$episode_id = self::source_episode_id( get_the_ID() );
		$image_id   = $episode_id ? (int) get_post_meta( $episode_id, 'ng_image_1200x630_id', true ) : 0;
		$src        = $image_id ? wp_get_attachment_image_src( $image_id, 'full' ) : false;
		return $src ? array( $src[0], (int) $src[1], (int) $src[2] ) : null;
	}

	public static function filter_facebook_tags( $meta ) {
		$image = self::share_image();
		if ( $image ) {
			$meta['og:image']            = $image[0];
			$meta['og:image:secure_url'] = $image[0];
			$meta['og:image:width']      = $image[1];
			$meta['og:image:height']     = $image[2];
		}
		return $meta;
	}

	public static function filter_twitter_tags( $meta ) {
		$image = self::share_image();
		if ( $image ) {
			$meta['twitter:image'] = $image[0];
		}
		return $meta;
	}

	public static function filter_description( $description ) {
		$episode_id = self::source_episode_id( get_the_ID() );
		if ( ! $episode_id ) {
			return $description;
		}

		$override = get_post_meta( $episode_id, 'ng_meta_aioseo_description', true );
		return $override ?: $description;
	}

	/**
	 * Pure: true when a submitted title/description is something a person wrote, not empty and not AIOSEO's default
	 * template (which carries smart tags such as "#post_title #separator_sa #site_title").
	 */
	public static function is_hand_written( $value ) {
		$value = trim( (string) $value );
		return '' !== $value && ! preg_match( '/#(?:[a-z]+_[a-z_]+|tagline|separator|site_title)\b/i', $value );
	}

	/**
	 * Pure: decides what AIOSEO saves for the SEO title and description.
	 *
	 * A hand-written value that differs from the stored one is the editor's own edit: it is kept, and returned under
	 * 'edited' so it can be written back to the episode record (otherwise the next publish or regeneration would put
	 * the generated text back, which is what happened to the 2026-10-21 edits on the Arbor episode). An empty value
	 * or AIOSEO's default template is filled from the stored (generated) text, as before. Returns
	 * array( 'title' => ..., 'description' => ..., 'edited' => array( field => value ) ).
	 */
	public static function resolve_save_fields( $submitted_title, $submitted_description, $stored_title, $stored_description ) {
		$out    = array( 'edited' => array() );
		$fields = array(
			'title'       => array( (string) $submitted_title, trim( (string) $stored_title ) ),
			'description' => array( (string) $submitted_description, trim( (string) $stored_description ) ),
		);
		foreach ( $fields as $key => $pair ) {
			list( $submitted, $stored ) = $pair;
			if ( self::is_hand_written( $submitted ) ) {
				$out[ $key ] = trim( $submitted );
				if ( trim( $submitted ) !== $stored ) {
					$out['edited'][ $key ] = trim( $submitted );
				}
			} else {
				$out[ $key ] = '' !== $stored ? $stored : $submitted;
			}
		}
		return $out;
	}

	/**
	 * aioseo_save_post: apply_filters( 'aioseo_save_post', array $data, Post $model ) - confirmed against
	 * AIOSEO Pro 5.0.3's Models/Post.php::savePost() on 2026-10-09. The FIRST argument is the plain ARRAY of
	 * fields about to be saved (keys such as 'title' and 'description'), the second AIOSEO's Post model.
	 *
	 * Fixed 2026-10-09: this was written for an object ("$post->title = ...", marked TODO(verify)) and fataled
	 * ("Attempt to assign property \"title\" on array") whenever an episode page was saved from the editor.
	 * Both shapes are handled now, and anything unexpected is returned untouched rather than risk a fatal.
	 *
	 * Reworked 2026-10-21: the generated title/description used to replace whatever was submitted, so an editor's
	 * own wording never stuck. Now a hand-written value wins and is mirrored to the episode record
	 * (resolve_save_fields), with ng_seo_hand_edited set so publishing and regeneration leave it alone.
	 */
	public static function filter_save_post( $data, $the_post = null ) {
		if ( ! is_array( $data ) && ! is_object( $data ) ) {
			return $data;
		}

		$wp_post_id = 0;
		if ( is_object( $the_post ) && isset( $the_post->post_id ) ) {
			$wp_post_id = (int) $the_post->post_id;
		}
		if ( ! $wp_post_id && is_array( $data ) && isset( $data['post_id'] ) ) {
			$wp_post_id = (int) $data['post_id'];
		}
		if ( ! $wp_post_id && is_object( $data ) && isset( $data->post_id ) ) {
			$wp_post_id = (int) $data->post_id;
		}
		if ( ! $wp_post_id && isset( $_POST['post_ID'] ) ) { // phpcs:ignore WordPress.Security.NonceVerification.Missing
			$wp_post_id = (int) $_POST['post_ID']; // phpcs:ignore WordPress.Security.NonceVerification.Missing
		}
		if ( ! $wp_post_id ) {
			$wp_post_id = (int) get_the_ID();
		}

		$episode_id = self::source_episode_id( $wp_post_id );
		if ( ! $episode_id ) {
			return $data;
		}

		$get = function ( $key ) use ( $data ) {
			return is_array( $data ) ? ( $data[ $key ] ?? '' ) : ( $data->$key ?? '' );
		};
		$resolved = self::resolve_save_fields(
			$get( 'title' ),
			$get( 'description' ),
			get_post_meta( $episode_id, 'ng_meta_aioseo_title', true ),
			get_post_meta( $episode_id, 'ng_meta_aioseo_description', true )
		);

		foreach ( array( 'title', 'description' ) as $key ) {
			if ( '' === (string) $resolved[ $key ] || (string) $resolved[ $key ] === (string) $get( $key ) ) {
				continue;
			}
			if ( is_array( $data ) ) {
				$data[ $key ] = $resolved[ $key ];
			} else {
				$data->$key = $resolved[ $key ];
			}
		}

		foreach ( $resolved['edited'] as $key => $value ) {
			update_post_meta( $episode_id, "ng_meta_aioseo_{$key}", $value );
		}
		if ( $resolved['edited'] ) {
			update_post_meta( $episode_id, 'ng_seo_hand_edited', current_time( 'mysql' ) );
		}

		return $data;
	}

	/**
	 * Writes the episode's SEO title and description into AIOSEO's own row for the public post. With no row of its
	 * own AIOSEO falls back to the Search Appearance template ("#post_title #separator_sa #site_title"), which
	 * appends the site name and pushes the title past the width AIOSEO scores as good; an explicit row keeps the
	 * generated title exactly as written. Called after every website publish and by the backfill. aioseo_save_post
	 * (filter_save_post) also fills both from the episode meta, so the arguments here only need to be non-empty.
	 */
	public static function sync_post( $wp_post_id, $episode_id ) {
		$title       = trim( (string) get_post_meta( $episode_id, 'ng_meta_aioseo_title', true ) );
		$description = trim( (string) get_post_meta( $episode_id, 'ng_meta_aioseo_description', true ) );
		if ( ! $wp_post_id || ( '' === $title && '' === $description ) || ! class_exists( '\\AIOSEO\\Plugin\\Common\\Models\\Post' ) ) {
			return false;
		}

		$data = array();
		if ( '' !== $title ) {
			$data['title'] = $title;
		}
		if ( '' !== $description ) {
			$data['description'] = $description;
		}

		try {
			\AIOSEO\Plugin\Common\Models\Post::savePost( (int) $wp_post_id, $data );
		} catch ( \Throwable $e ) {
			return false;
		}
		return true;
	}

	private static function source_episode_id( $wp_post_id ) {
		if ( ! $wp_post_id ) {
			return 0;
		}
		return (int) get_post_meta( $wp_post_id, '_ng_source_episode_id', true );
	}
}
