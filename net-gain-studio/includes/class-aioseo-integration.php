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
	 * aioseo_save_post: apply_filters( 'aioseo_save_post', array $data, Post $model ) - confirmed against
	 * AIOSEO Pro 5.0.3's Models/Post.php::savePost() on 2026-10-09. The FIRST argument is the plain ARRAY of
	 * fields about to be saved (keys such as 'title' and 'description'), the second AIOSEO's Post model.
	 *
	 * Fixed 2026-10-09: this was written for an object ("$post->title = ...", marked TODO(verify)) and fataled
	 * ("Attempt to assign property \"title\" on array") whenever an episode page was saved from the editor.
	 * Both shapes are handled now, and anything unexpected is returned untouched rather than risk a fatal.
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

		$overrides = array(
			'title'       => get_post_meta( $episode_id, 'ng_meta_aioseo_title', true ),
			'description' => get_post_meta( $episode_id, 'ng_meta_aioseo_description', true ),
		);
		foreach ( $overrides as $key => $value ) {
			if ( ! $value ) {
				continue;
			}
			if ( is_array( $data ) ) {
				$data[ $key ] = $value;
			} else {
				$data->$key = $value;
			}
		}

		return $data;
	}

	private static function source_episode_id( $wp_post_id ) {
		if ( ! $wp_post_id ) {
			return 0;
		}
		return (int) get_post_meta( $wp_post_id, '_ng_source_episode_id', true );
	}
}
