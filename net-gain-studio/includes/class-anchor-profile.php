<?php
/**
 * Anchor profiles: the extra fields a show's anchor needs beyond what a
 * WordPress user already has, plus the one place that turns an anchor into
 * schema.org Person data.
 *
 * "Anchor" is the public term (decided 2026-10-08) for whoever voices an
 * episode; the underlying data is still a WordPress user with the ng_talent
 * role and rows in the talent-assignments table (Spec Section 4). The bio
 * itself is WordPress's own "Biographical Info" field; only what WordPress
 * has no field for lives here.
 *
 * The Person @id deliberately matches the one AIOSEO already publishes
 * ({author URL}#author), so an episode's author and the bio page's subject
 * resolve to one entity rather than two near-duplicates.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Anchor_Profile {

	const META_KEYS = array(
		'ng_anchor_title',
		'ng_anchor_covers',
		'ng_anchor_since',
		'ng_anchor_photo',
		'ng_anchor_linkedin',
		'ng_anchor_website',
	);

	public static function register() {
		add_action( 'show_user_profile', array( __CLASS__, 'render_fields' ) );
		add_action( 'edit_user_profile', array( __CLASS__, 'render_fields' ) );
		add_action( 'personal_options_update', array( __CLASS__, 'save_fields' ) );
		add_action( 'edit_user_profile_update', array( __CLASS__, 'save_fields' ) );
		add_filter( 'aioseo_schema_output', array( __CLASS__, 'enrich_aioseo_graph' ) );
		add_action( 'wp_head', array( __CLASS__, 'output_fallback_schema' ) );
	}

	private static function is_anchor_user( $user ) {
		if ( in_array( 'ng_talent', (array) $user->roles, true ) ) {
			return true;
		}
		return (bool) Net_Gain_Talent_Assignments::list_for_user( $user->ID );
	}

	public static function render_fields( $user ) {
		if ( ! self::is_anchor_user( $user ) ) {
			return;
		}

		$value = function ( $key ) use ( $user ) {
			return esc_attr( (string) get_user_meta( $user->ID, $key, true ) );
		};
		?>
		<h2>Anchor profile</h2>
		<p class="description" style="max-width:640px">Shown on this anchor's public bio page and in the structured data search engines read. The bio itself is the "Biographical Info" field above.</p>
		<table class="form-table" role="presentation">
			<tr>
				<th><label for="ng_anchor_title">Credential line</label></th>
				<td><input type="text" class="regular-text" id="ng_anchor_title" name="ng_anchor_title" value="<?php echo $value( 'ng_anchor_title' ); ?>"><p class="description">One line under the name, e.g. "Technology journalist and analyst".</p></td>
			</tr>
			<tr>
				<th><label for="ng_anchor_covers">Covers</label></th>
				<td><input type="text" class="regular-text" id="ng_anchor_covers" name="ng_anchor_covers" value="<?php echo $value( 'ng_anchor_covers' ); ?>"><p class="description">Comma-separated topics, e.g. "Edtech, security, policy".</p></td>
			</tr>
			<tr>
				<th><label for="ng_anchor_since">Anchoring since</label></th>
				<td><input type="text" class="regular-text" id="ng_anchor_since" name="ng_anchor_since" value="<?php echo $value( 'ng_anchor_since' ); ?>"><p class="description">e.g. "September 2026".</p></td>
			</tr>
			<tr>
				<th><label for="ng_anchor_photo">Photo URL</label></th>
				<td><input type="url" class="regular-text" id="ng_anchor_photo" name="ng_anchor_photo" value="<?php echo $value( 'ng_anchor_photo' ); ?>"><p class="description">Upload the photo in the Media Library and paste its URL. Square works best. Leave empty to show initials.</p></td>
			</tr>
			<tr>
				<th><label for="ng_anchor_linkedin">LinkedIn URL</label></th>
				<td><input type="url" class="regular-text" id="ng_anchor_linkedin" name="ng_anchor_linkedin" value="<?php echo $value( 'ng_anchor_linkedin' ); ?>"></td>
			</tr>
			<tr>
				<th><label for="ng_anchor_website">Website URL</label></th>
				<td><input type="url" class="regular-text" id="ng_anchor_website" name="ng_anchor_website" value="<?php echo $value( 'ng_anchor_website' ); ?>"></td>
			</tr>
		</table>
		<?php
	}

	public static function save_fields( $user_id ) {
		// WordPress has already verified its own update-user nonce by the time
		// these hooks fire; only the capability needs checking here.
		if ( ! current_user_can( 'edit_user', $user_id ) ) {
			return;
		}

		$url_keys = array( 'ng_anchor_photo', 'ng_anchor_linkedin', 'ng_anchor_website' );

		foreach ( self::META_KEYS as $key ) {
			if ( ! isset( $_POST[ $key ] ) ) {
				continue;
			}
			$raw   = wp_unslash( $_POST[ $key ] );
			$clean = in_array( $key, $url_keys, true ) ? esc_url_raw( $raw ) : sanitize_text_field( $raw );
			update_user_meta( $user_id, $key, $clean );
		}
	}

	/**
	 * Everything the theme and the schema need about one anchor, in one place.
	 * 'kind' is 'anchor' for a show's primary, 'guest' for someone who only
	 * covers (a substitute row), '' for anyone with no assignment.
	 */
	public static function profile( $user_id ) {
		$user = get_userdata( $user_id );
		if ( ! $user ) {
			return null;
		}

		$shows = array();
		$kind  = '';
		foreach ( Net_Gain_Talent_Assignments::list_for_user( $user_id ) as $row ) {
			$show_id = (int) $row['show_id'];
			$shows[] = array(
				'id'    => $show_id,
				'slug'  => get_post_field( 'post_name', $show_id ),
				'title' => get_the_title( $show_id ),
				'role'  => $row['role'],
			);
			if ( 'primary' === $row['role'] ) {
				$kind = 'anchor';
			} elseif ( '' === $kind ) {
				$kind = 'guest';
			}
		}

		$covers = array_values( array_filter( array_map( 'trim', explode( ',', (string) get_user_meta( $user_id, 'ng_anchor_covers', true ) ) ) ) );

		return array(
			'id'       => (int) $user_id,
			'name'     => $user->display_name,
			'url'      => get_author_posts_url( $user_id ),
			'title'    => (string) get_user_meta( $user_id, 'ng_anchor_title', true ),
			'bio'      => (string) get_user_meta( $user_id, 'description', true ),
			'covers'   => $covers,
			'since'    => (string) get_user_meta( $user_id, 'ng_anchor_since', true ),
			'photo'    => (string) get_user_meta( $user_id, 'ng_anchor_photo', true ),
			'linkedin' => (string) get_user_meta( $user_id, 'ng_anchor_linkedin', true ),
			'website'  => (string) get_user_meta( $user_id, 'ng_anchor_website', true ),
			'shows'    => $shows,
			'kind'     => $kind,
		);
	}

	/** schema.org Person for an anchor (no @context - callers embed it). */
	public static function person_schema( $user_id ) {
		$p = self::profile( $user_id );
		if ( ! $p ) {
			return null;
		}

		$person = array(
			'@type' => 'Person',
			'@id'   => $p['url'] . '#author',
			'name'  => $p['name'],
			'url'   => $p['url'],
		);

		if ( $p['shows'] ) {
			$show_titles = implode( ' and ', array_unique( wp_list_pluck( $p['shows'], 'title' ) ) );
			$person['jobTitle'] = ( 'guest' === $p['kind'] ? 'Guest anchor, ' : 'Anchor, ' ) . $show_titles;
		}

		$description = '' !== trim( $p['bio'] ) ? wp_strip_all_tags( $p['bio'] ) : $p['title'];
		$description = trim( preg_replace( '/\s+/u', ' ', $description ) );
		if ( '' !== $description ) {
			$person['description'] = mb_strlen( $description ) > 300 ? mb_substr( $description, 0, 297 ) . '...' : $description;
		}

		$person['worksFor'] = array( '@id' => home_url( '/#organization' ) );

		if ( '' !== $p['photo'] ) {
			$person['image'] = $p['photo'];
		}

		$same_as = array_values( array_filter( array( $p['linkedin'], $p['website'] ) ) );
		if ( $same_as ) {
			$person['sameAs'] = $same_as;
		}

		if ( $p['covers'] ) {
			$person['knowsAbout'] = $p['covers'];
		}

		return $person;
	}

	/** The anchor whose Person entity the current page describes (bio page, or an episode's author), or 0. */
	private static function context_user_id() {
		if ( is_author() ) {
			return (int) get_queried_object_id();
		}
		if ( is_singular( 'podcast' ) ) {
			return (int) get_post_field( 'post_author', get_the_ID() );
		}
		return 0;
	}

	/**
	 * AIOSEO already publishes a Person ({author URL}#author) and, on the bio
	 * page, a ProfilePage pointing at it - but the Person is only a name and a
	 * Gravatar. Merge the anchor's role, bio, topics and profile links into that
	 * same node rather than adding a second, conflicting one. With no photo set,
	 * drop AIOSEO's Gravatar image: it is the generic silhouette for anyone
	 * without a Gravatar, which is worse than no image.
	 */
	public static function enrich_aioseo_graph( $graphs ) {
		$user_id = self::context_user_id();
		if ( ! $user_id || ! is_array( $graphs ) ) {
			return $graphs;
		}

		$person = self::person_schema( $user_id );
		if ( ! $person ) {
			return $graphs;
		}

		foreach ( $graphs as $i => $node ) {
			if ( is_array( $node ) && isset( $node['@type'], $node['@id'] ) && 'Person' === $node['@type'] && $person['@id'] === $node['@id'] ) {
				$extra = $person;
				unset( $extra['@type'], $extra['@id'], $extra['name'], $extra['url'] );
				if ( ! isset( $extra['image'] ) ) {
					unset( $node['image'] );
				}
				$graphs[ $i ] = array_merge( $node, $extra );
			}
		}

		return $graphs;
	}

	/** Only when AIOSEO is not active to publish the entity itself: a Person on the bio page. */
	public static function output_fallback_schema() {
		if ( ! is_author() || defined( 'AIOSEO_VERSION' ) || function_exists( 'aioseo' ) ) {
			return;
		}

		$person = self::person_schema( get_queried_object_id() );
		if ( ! $person ) {
			return;
		}

		$schema = array_merge( array( '@context' => 'https://schema.org' ), $person );
		$json   = str_replace( '</script>', '<\/script>', wp_json_encode( $schema ) );
		echo '<script type="application/ld+json">' . $json . "</script>\n";
	}
}
