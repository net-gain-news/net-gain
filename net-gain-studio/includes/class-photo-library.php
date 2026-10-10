<?php
/**
 * Photo library (per show): real photographs the pipeline turns into episode graphics (duotone, varied crops,
 * the show's frames). Added 2026-10-09 when the code-built cards read as "too techy" for the edtech audience.
 *
 * Design notes
 *  - One `ng_photo` post per photo, post_parent = the show, so every library is per show (a second vertical gets its
 *    own). Posts are internal only (no UI, no REST exposure of their own); the admin screen and the pipeline use the
 *    custom routes in class-rest-photos.php.
 *  - ORIGINALS ARE NEVER PUBLIC. The operator sources photos from Envato Elements, whose licence forbids handing the
 *    raw file out, so originals and the admin previews live in a private directory outside the web root and are
 *    streamed only through permission-checked REST routes. Only the finished, duotoned, cropped graphics the pipeline
 *    uploads to the media library are public. If no directory outside the web root is writable, a protected folder
 *    inside wp-content is used and the admin screen shows a warning.
 *  - Real photos only: uploads whose embedded metadata declares AI generation (IPTC DigitalSourceType, known
 *    generators) are rejected. This is a limited, honest check of declared provenance, not a detector.
 *  - A photo is "eligible" when it is ready and not used within the show's cooldown (default 90 days). Reuse after the
 *    cooldown is expected: with a cooldown, a library of ~150 photos lasts indefinitely, and every reuse gets a
 *    different crop and treatment (decided in the pipeline).
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Photo_Library {

	const POST_TYPE = 'ng_photo';

	const STATUS_PENDING = 'pending_tags'; // uploaded, waiting for the pipeline's vision tagging
	const STATUS_READY   = 'ready';
	const STATUS_RETIRED = 'retired';

	const DEFAULT_COOLDOWN_DAYS = 90;
	const MIN_SHORT_SIDE        = 800;   // reject below this
	const LOW_RES_SHORT_SIDE    = 2200;  // flag below this (square crops need roughly this much)
	const MAX_BYTES             = 52428800; // 50 MB

	/** Story topics a photo can suit; mirrored in pipeline/photo_library.py (TOPICS). 'general' suits any story. */
	const TOPICS = array( 'security', 'ai', 'policy', 'funding', 'business', 'product', 'higher_ed', 'k12', 'general' );

	/** Who is visible in the photo: matters for sensitive stories (breaches, safety, lawsuits). */
	const PEOPLE = array( 'none', 'anonymous', 'identifiable' );

	/** Declared-AI markers in a file's metadata (case-insensitive substring match against the head of the file). */
	const AI_MARKERS = array(
		'algorithmicmedia',     // IPTC DigitalSourceType: trainedAlgorithmicMedia, compositeWithTrainedAlgorithmicMedia, ...
		'midjourney',
		'dall-e',
		"dall\xc2\xb7e",
		'stable diffusion',
		'stablediffusion',
		'adobe firefly',
		'made with google ai',
		'openai',
	);

	public static function register() {
		register_post_type(
			self::POST_TYPE,
			array(
				'label'        => 'Photos',
				'public'       => false,
				'show_ui'      => false,
				'show_in_menu' => false,
				'show_in_rest' => false,
				'supports'     => array( 'title' ),
				'hierarchical' => true,
				'rewrite'      => false,
			)
		);
	}

	// --- private storage ------------------------------------------------------------------------

	/** The private directory (created on demand). Returns array( path, outside_webroot ). */
	public static function private_dir() {
		$candidates = array(
			array( dirname( untrailingslashit( ABSPATH ) ) . '/ng-private/photos', true ),
			array( WP_CONTENT_DIR . '/ng-private/photos', false ),
		);
		foreach ( $candidates as $candidate ) {
			list( $dir, $outside ) = $candidate;
			if ( ( is_dir( $dir ) || @wp_mkdir_p( $dir ) ) && is_writable( $dir ) ) { // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
				if ( ! $outside ) {
					self::protect_dir( dirname( $dir ) );
					self::protect_dir( $dir );
				}
				return array( $dir, $outside );
			}
		}
		return array( '', false );
	}

	private static function protect_dir( $dir ) {
		if ( ! is_dir( $dir ) ) {
			return;
		}
		if ( ! file_exists( $dir . '/.htaccess' ) ) {
			@file_put_contents( $dir . '/.htaccess', "Require all denied\nDeny from all\n" ); // phpcs:ignore
		}
		if ( ! file_exists( $dir . '/index.html' ) ) {
			@file_put_contents( $dir . '/index.html', '' ); // phpcs:ignore
		}
	}

	public static function file_path( $relative ) {
		list( $dir ) = self::private_dir();
		$relative    = ltrim( (string) $relative, '/' );
		if ( ! $dir || '' === $relative || false !== strpos( $relative, '..' ) ) {
			return '';
		}
		return $dir . '/' . $relative;
	}

	// --- upload checks (pure: unit-tested with php CLI) -------------------------------------------

	/** Declared-AI markers found in the first and last 256 KB of the file bytes. Empty array = none declared. */
	public static function scan_provenance( $bytes ) {
		$head  = strtolower( substr( $bytes, 0, 262144 ) . substr( $bytes, -262144 ) );
		$found = array();
		foreach ( self::AI_MARKERS as $marker ) {
			if ( false !== strpos( $head, strtolower( $marker ) ) ) {
				$found[] = $marker;
			}
		}
		return $found;
	}

	/** Returns '' if the dimensions are acceptable, else a plain-language reason. */
	public static function check_dimensions( $width, $height ) {
		if ( min( $width, $height ) < self::MIN_SHORT_SIDE ) {
			return sprintf( 'Too small (%d×%d px). Photos need at least %d px on the short side; ideally 4000×2700 or larger.', $width, $height, self::MIN_SHORT_SIDE );
		}
		return '';
	}

	public static function is_low_res( $width, $height ) {
		return min( (int) $width, (int) $height ) < self::LOW_RES_SHORT_SIDE;
	}

	// --- eligibility and stats (pure) ------------------------------------------------------------

	/**
	 * @param array  $photo         needs 'status' and 'last_used' (Y-m-d or '').
	 * @param int    $cooldown_days
	 * @param string $for_date      Y-m-d the graphic is for.
	 * @return array { eligible: bool, days_since: int|null, available_on: string|null }
	 */
	public static function eligibility( $photo, $cooldown_days, $for_date ) {
		if ( ( $photo['status'] ?? '' ) !== self::STATUS_READY ) {
			return array( 'eligible' => false, 'days_since' => null, 'available_on' => null );
		}
		$last = $photo['last_used'] ?? '';
		if ( '' === $last ) {
			return array( 'eligible' => true, 'days_since' => null, 'available_on' => null );
		}
		$days_since = (int) floor( ( strtotime( $for_date . ' UTC' ) - strtotime( $last . ' UTC' ) ) / 86400 );
		$available  = gmdate( 'Y-m-d', strtotime( $last . ' UTC' ) + ( (int) $cooldown_days * 86400 ) );
		return array(
			'eligible'     => $days_since >= (int) $cooldown_days,
			'days_since'   => $days_since,
			'available_on' => $available,
		);
	}

	/**
	 * Library health for the admin meter and the weekly email.
	 *
	 * @param array[] $photos         each: status, last_used, topics[], people.
	 * @param int     $cooldown_days
	 * @param string  $for_date       Y-m-d (today).
	 * @param int     $episodes_per_week
	 */
	public static function stats( $photos, $cooldown_days, $for_date, $episodes_per_week ) {
		$out = array(
			'total'                  => count( $photos ),
			'ready'                  => 0,
			'pending'                => 0,
			'retired'                => 0,
			'never_used'             => 0,
			'eligible_now'           => 0,
			'cooling_down'           => 0,
			'eligible_no_faces'      => 0,
			'eligible_by_topic'      => array_fill_keys( self::TOPICS, 0 ),
			'low_res'                => 0,
			'episodes_per_week'      => max( 0, (int) $episodes_per_week ),
			'cooldown_days'          => (int) $cooldown_days,
		);

		foreach ( $photos as $photo ) {
			$status = $photo['status'] ?? '';
			if ( self::STATUS_PENDING === $status ) {
				$out['pending']++;
				continue;
			}
			if ( self::STATUS_RETIRED === $status ) {
				$out['retired']++;
				continue;
			}
			if ( self::STATUS_READY !== $status ) {
				continue;
			}
			$out['ready']++;
			if ( ! empty( $photo['flags'] ) && in_array( 'low_res', (array) $photo['flags'], true ) ) {
				$out['low_res']++;
			}
			if ( '' === ( $photo['last_used'] ?? '' ) ) {
				$out['never_used']++;
			}
			$e = self::eligibility( $photo, $cooldown_days, $for_date );
			if ( ! $e['eligible'] ) {
				$out['cooling_down']++;
				continue;
			}
			$out['eligible_now']++;
			if ( in_array( $photo['people'] ?? 'none', array( 'none', 'anonymous' ), true ) ) {
				$out['eligible_no_faces']++;
			}
			$topics = (array) ( $photo['topics'] ?? array() );
			foreach ( self::TOPICS as $topic ) {
				if ( 'general' === $topic || in_array( $topic, $topics, true ) || in_array( 'general', $topics, true ) ) {
					$out['eligible_by_topic'][ $topic ]++;
				}
			}
		}

		$pace = $out['episodes_per_week'];
		$out['weeks_of_cover'] = $pace > 0 ? round( $out['eligible_now'] / $pace, 1 ) : null;

		$messages = array();
		$level    = 'ok';
		if ( 0 === $out['ready'] ) {
			$level      = 'urgent';
			$messages[] = 'The library has no ready photos. New episodes cannot get graphics until some are added.';
		} else {
			$cover = $out['weeks_of_cover'];
			if ( null !== $cover && $cover < 3 ) {
				$level = 'urgent';
			} elseif ( null !== $cover && $cover < 6 ) {
				$level = 'low';
			}
			if ( null !== $cover ) {
				$messages[] = sprintf( '%d photos are ready to use now (about %s weeks of episodes before reuse is needed).', $out['eligible_now'], rtrim( rtrim( number_format( $cover, 1 ), '0' ), '.' ) );
			}
			if ( $out['eligible_no_faces'] < 3 ) {
				$level      = 'urgent' === $level ? 'urgent' : 'low';
				$messages[] = sprintf( 'Only %d eligible photos without identifiable people. Sensitive stories (breaches, safety, lawsuits) can use only those. Add laptops, hands, hallways, buildings or people seen from behind.', $out['eligible_no_faces'] );
			}
			$thin = array();
			foreach ( array( 'security', 'ai', 'policy', 'funding', 'higher_ed', 'k12' ) as $topic ) {
				if ( $out['eligible_by_topic'][ $topic ] < 3 ) {
					$thin[] = str_replace( '_', ' ', $topic );
				}
			}
			if ( $thin ) {
				$messages[] = 'Thin on photos suited to: ' . implode( ', ', $thin ) . '.';
			}
		}
		if ( $out['pending'] > 0 ) {
			$messages[] = sprintf( '%d photo(s) are still being tagged.', $out['pending'] );
		}
		$out['level']    = $level;
		$out['messages'] = $messages;
		return $out;
	}

	// --- records ---------------------------------------------------------------------------------

	public static function episodes_per_week( $show_id ) {
		$days = get_post_meta( $show_id, 'ng_recording_days', true );
		return is_array( $days ) && $days ? count( $days ) : 5;
	}

	public static function cooldown_days( $show_id ) {
		$value = (int) get_post_meta( $show_id, 'ng_photo_cooldown_days', true );
		return $value > 0 ? $value : self::DEFAULT_COOLDOWN_DAYS;
	}

	/** One photo post as the array the admin screen and the pipeline use. */
	public static function to_array( $post, $cooldown_days = null, $for_date = null ) {
		$id   = $post->ID;
		$show = (int) $post->post_parent;
		$meta = function ( $key, $default = '' ) use ( $id ) {
			$value = get_post_meta( $id, $key, true );
			return ( '' === $value || null === $value ) ? $default : $value;
		};

		$photo = array(
			'id'            => $id,
			'show_id'       => $show,
			'name'          => $meta( 'ng_photo_original_name' ),
			'status'        => $meta( 'ng_photo_status', self::STATUS_PENDING ),
			'width'         => (int) $meta( 'ng_photo_width', 0 ),
			'height'        => (int) $meta( 'ng_photo_height', 0 ),
			'tags'          => array_values( (array) $meta( 'ng_photo_tags', array() ) ),
			'topics'        => array_values( (array) $meta( 'ng_photo_topics', array() ) ),
			'people'        => $meta( 'ng_photo_people', '' ),
			'focal_x'       => (float) $meta( 'ng_photo_focal_x', 0.5 ),
			'focal_y'       => (float) $meta( 'ng_photo_focal_y', 0.5 ),
			'description'   => $meta( 'ng_photo_description' ),
			'flags'         => array_values( (array) $meta( 'ng_photo_flags', array() ) ),
			'use_count'     => (int) $meta( 'ng_photo_use_count', 0 ),
			'last_used'     => $meta( 'ng_photo_last_used' ),
			'used_on'       => array_values( (array) $meta( 'ng_photo_used_on', array() ) ),
			'added'         => substr( $post->post_date_gmt ?: $post->post_date, 0, 10 ),
			'thumb_url'     => rest_url( 'net-gain/v1/photos/' . $id . '/thumb' ),
		);

		if ( null !== $cooldown_days && null !== $for_date ) {
			$photo = array_merge( $photo, self::eligibility( $photo, $cooldown_days, $for_date ) );
		}
		return $photo;
	}

	public static function list_for_show( $show_id, $cooldown_days = null, $for_date = null ) {
		$posts = get_posts(
			array(
				'post_type'      => self::POST_TYPE,
				'post_status'    => 'any',
				'post_parent'    => $show_id,
				'posts_per_page' => 1000,
				'orderby'        => 'date',
				'order'          => 'DESC',
			)
		);
		return array_map(
			function ( $post ) use ( $cooldown_days, $for_date ) {
				return self::to_array( $post, $cooldown_days, $for_date );
			},
			$posts
		);
	}

	/** Records that a photo was used for an episode. Idempotent per episode (a re-render must not count twice). */
	public static function record_use( $photo_id, $episode_id, $date ) {
		$used = (array) get_post_meta( $photo_id, 'ng_photo_used_on', true );
		foreach ( $used as $entry ) {
			if ( (int) ( $entry['episode_id'] ?? 0 ) === (int) $episode_id ) {
				return false;
			}
		}
		$used[] = array( 'episode_id' => (int) $episode_id, 'date' => $date );
		$dates  = array_filter( array_map( function ( $e ) { return $e['date'] ?? ''; }, $used ) );
		rsort( $dates );
		update_post_meta( $photo_id, 'ng_photo_used_on', $used );
		update_post_meta( $photo_id, 'ng_photo_use_count', count( $used ) );
		update_post_meta( $photo_id, 'ng_photo_last_used', $dates ? $dates[0] : $date );
		return true;
	}
}
